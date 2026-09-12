# Agente de vuelos directos CDMX → Madrid




## Fuentes (dos, ambas gratis y sin cuenta)

| Fuente | Qué aporta |
|---|---|
| **Google Flights** | tarifas de las aerolíneas. Búsqueda general **más una por aerolínea** (Iberia, Aeroméxico, Air Europa, World2Fly): la general sola escondía a Iberia, ~$4,300 MXN más barata. |
| **Kiwi.com** | tarifas de agencias que Google no siempre muestra. |
| **Booking.com** | además de sus tarifas, es la única que expone el **costo de agregar la maleta**, lo que permite comparar "tarifa básica + maleta" contra "tarifa con maleta incluida". |
| **2 sencillos** | compra la ida y la vuelta por separado, incluso en aerolíneas distintas. Gana cuando una de las dos fechas está cara. |
| **Kiwi multi-mercado** | el mismo vuelo comprado desde España, EE.UU. o Reino Unido, convertido a pesos al tipo de cambio del BCE. |

### Hacks que el agente aplica
- **Barrido por aerolínea:** Google recorta la lista de resultados y esconde tarifas; se le pregunta por cada aerolínea por separado.
- **Ida y vuelta por separado:** se reporta solo si gana, y advirtiendo que son dos boletos independientes.
- **Precio final, no precio de anzuelo:** una tarifa básica de Booking salía en $31,353 pero sin maleta; sumando los $3,788 de documentar, el total real era $35,141. El agente siempre compara con la maleta ya incluida.
- **Tendencia propia:** con el historial acumulado en `data/history.jsonl` el agente te dice si el precio de hoy está bajo o alto *para esta ruta*, algo que ninguna fuente externa sabe.
- **Arbitraje de punto de venta:** solo se reporta si el ahorro pasa del 3%, porque abajo de eso se lo come la comisión por conversión de divisa de tu tarjeta.

### Hacks que el agente NO usa, a propósito
- **Hidden city / throwaway ticketing** (bajarte en la escala): sale barato pero no puedes documentar maleta, la aerolínea puede cancelarte el regreso y hasta cerrarte el programa de viajero frecuente. Con maleta de 23 kg, no aplica.
- **Conexiones por tu cuenta:** si pierdes el enlace, nadie te reacomoda.

Las dos se consultan en cada revisión y se combinan quedándose con el precio más
bajo de cada vuelo. **Si una falla, la otra sigue trabajando**; solo si ninguna
responde te llega un aviso de error (máximo uno al día).

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
