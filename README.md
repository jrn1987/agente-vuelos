# Agente de vuelos CDMX → Madrid y San Francisco




## Fuentes (todas gratis y sin cuenta)

> **Amadeus ya no está.** Cerró su API gratuita Self-Service el 17 de julio de 2026:
> `test.api.amadeus.com` no resuelve y producción responde 410. Su proveedor se
> eliminó del repo para no dejar código muerto.

| Fuente | Qué aporta |
|---|---|
| **Google Flights** | tarifas de las aerolíneas. Búsqueda general **más una por aerolínea** (Iberia, Aeroméxico, Air Europa, World2Fly): la general sola escondía a Iberia, ~$4,300 MXN más barata. |
| **Kiwi.com** | tarifas de agencias que Google no siempre muestra. |
| **Booking.com** | además de sus tarifas, es la única que expone el **costo de agregar la maleta**, lo que permite comparar "tarifa básica + maleta" contra "tarifa con maleta incluida". |
| **Aviasales (Travelpayouts)** | agrega decenas de agencias con buena cobertura en Latinoamérica. Devuelve precios de **caché**, no en vivo, así que sirve para detectar que una tarifa existe y confirmarla en el enlace; va marcada como tal y nunca encabeza el correo si hay un precio en vivo. Solo aporta **directos**, porque su respuesta no dice cuánto dura cada escala y el límite de 6 h no se podría verificar. |
| **Booking multi-mercado** | el mismo vuelo comprado desde España, EE.UU. o Reino Unido, convertido a pesos al tipo de cambio del BCE. Solo se reporta si el ahorro pasa del 3%. |
| **2 sencillos** | compra la ida y la vuelta por separado, incluso en aerolíneas distintas. Gana cuando una de las dos fechas está cara. |
| **Kiwi multi-mercado** | el mismo vuelo comprado desde España, EE.UU. o Reino Unido, convertido a pesos al tipo de cambio del BCE. |

### Hacks que el agente aplica
- **Barrido por aerolínea:** Google recorta la lista de resultados y esconde tarifas; se le pregunta por cada aerolínea por separado.
- **Ida y vuelta por separado:** se reporta solo si gana, y advirtiendo que son dos boletos independientes.
- **Maleta siempre sumada:** si una tarifa no incluye maleta documentada, el agente usa el precio real que cotice el vendedor y, si no lo cotiza, lo estima con la tabla de `equipaje.py` — siempre avisando que **se compra por separado**. Así todas las opciones se comparan con el mismo total.
- **Comprar directo con la aerolínea:** cada correo trae el enlace al buscador de la aerolínea, porque ahí es donde aplican los MSI de BBVA y Amex.
- **Precio final, no precio de anzuelo:** una tarifa básica de Booking salía en $31,353 pero sin maleta; sumando los $3,788 de documentar, el total real era $35,141. El agente siempre compara con la maleta ya incluida.
- **Tendencia propia:** con el historial acumulado en `data/history.jsonl` el agente te dice si el precio de hoy está bajo o alto *para esta ruta*, algo que ninguna fuente externa sabe.
- **Arbitraje de punto de venta:** solo se reporta si el ahorro pasa del 3%, porque abajo de eso se lo come la comisión por conversión de divisa de tu tarjeta.

### Buscadores que se probaron y no sirven
Iberia y Aeroméxico bloquean el acceso automático (403 de Akamai / página de
mantenimiento), igual que Despegar, Trip.com, Kayak y Momondo (captcha o redirección).
Expedia responde pero con límite de peticiones. Por eso el agente no lee precios
directo de las aerolíneas: en su lugar te deja el enlace para comprar ahí.

### Boletos separados
Están activados (`allow_separate_tickets`), y el agente los marca siempre con
`BOLETOS SEPARADOS` porque el riesgo es real y concreto:

- En la escala **recoges la maleta y la vuelves a documentar**: no viaja de corrido.
- Pasas migración del país de la escala, así que puede hacer falta visa de tránsito.
- Si el primer vuelo se retrasa, **nadie te reacomoda** en el segundo: pierdes ese boleto.

Por eso el correo pone el aviso arriba cuando la opción más barata es de este tipo,
para que la compares contra la mejor de un solo boleto antes de decidir.

### Hacks que el agente NO usa, a propósito
- **Hidden city / throwaway ticketing** (bajarte en la escala): sale barato pero no puedes documentar maleta, la aerolínea puede cancelarte el regreso y hasta cerrarte el programa de viajero frecuente. Con maleta de 23 kg, no aplica.

Todas se consultan en cada revisión y se combinan quedándose con el precio más
bajo de cada vuelo. **Si una falla, la otra sigue trabajando**; solo si ninguna
responde te llega un aviso de error (máximo uno al día).

## Rutas vigiladas
El agente sigue varias rutas a la vez (`routes` en `config.json`), cada una con
su propio objetivo de precio, su historial y sus avisos:

| Ruta | Criterio | Objetivo | Fuentes |
|---|---|---|---|
| **Madrid** | directos y 1 escala ≤6 h, con maleta | $25,000 | las 10 |
| **San Francisco** | **solo directos**, con maleta | $11,000 | Google, Booking, SerpAPI |

San Francisco usa menos fuentes a propósito: las multi-mercado y de caché no
aportan en esa ruta y solo gastarían ritmo contra los mismos servidores.

Cada ruta manda su propio correo cuando tiene novedades, así que un movimiento
en Madrid no se confunde con uno en San Francisco.

## Plan B: otros destinos
`plan_b.py` cotiza **vuelos directos con maleta** a Los Ángeles, Nueva York,
Chicago, París y Tokio en las mismas fechas, y el correo los compara contra
Madrid con barras proporcionales. Se cotizan **solo cuando va a salir un correo**
(5 consultas por correo, no por revisión), que es la lección que dejó el bloqueo
de Booking.

## Diseño del correo
`correo.py` arma el correo en HTML con tablas y estilos en línea, porque Gmail y
Outlook ignoran `<style>` y no soportan flexbox ni grid. Va ordenado por la
prioridad real de decisión:

El **directo con maleta encabeza el correo**: su precio va en la cabecera, y si
otra opción es más barata se menciona ahí con un puntero a su sección, en vez de
desplazarlo. Cada opción trae su **botón directo a la oferta**; los itinerarios
de dos boletos llevan un enlace por tramo, porque son dos compras distintas.

1. **Directo con maleta** — un solo boleto, sin conexiones.
2. **Multi-aerolínea directo** — ida y vuelta directas, compradas por separado.
3. **Con escala** — ninguna escala pasa de `max_layover_hours`, ni en la ida ni
   en la vuelta; cada escala se muestra con su duración y su aeropuerto.

Arriba van tres tarjetas de resumen (directo con maleta, la más barata, tu
objetivo), y más abajo una gráfica de barras con el precio mínimo de cada día.
Las barras se dibujan con tablas HTML, no con imágenes ni SVG: los clientes de
correo bloquean las imágenes remotas y Outlook no renderiza SVG.

Si una categoría no tiene resultados, lo dice en vez de desaparecer. Si el diseño
fallara, el correo cae a una versión de texto simple en lugar de no enviarse.

## Niveles de aviso

| Nivel | Cuándo | Asunto |
|---|---|---|
| 🚨 **Alerta mayor** | total **por debajo de $25,000 MXN** | `🚨 ¡VUELO BUENO!` |
| 🔻 Nuevo mínimo | mejor precio visto, al menos 1% abajo del anterior | `🔻 NUEVO MÍNIMO` |
| 📊 Resumen | una vez al día a las 9 am (hora CDMX) | `📊 Resumen diario` |
| 🔻 Bajó | **cualquier** bajada contra la revisión anterior | `🔻 Bajó de precio` |
| ➡️ Sigue igual | está en el precio de referencia o por debajo (una vez por nivel de precio al día) | `➡️ Sigue en $X` |
| ✅ Latido | 24 h sin haberte escrito nada | `✅ Sigo vigilando` |

Todos los correos incluyen las opciones de **meses sin intereses con BBVA y American Express** (ver `msi.py`).

Tope de 8 correos al día. La alerta mayor se repite solo si el precio mejora aún más.

## Equipaje
La búsqueda aplica el filtro de Google Flights de **1 maleta documentada**, así que
los precios ya la incluyen. En transatlánticos de estas aerolíneas la franquicia
estándar es de **23 kg** (arriba de los 20 kg pedidos). Verifica siempre en el
checkout antes de pagar: las tarifas cambian de condiciones sin aviso.

nvío del correo
- `config.json` — tus parámetros (sin contraseñas)
- `data/history.jsonl` — historial de precios de cada revisión
