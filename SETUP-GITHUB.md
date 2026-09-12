# Ponerlo en GitHub Actions (gratis, 24/7, sin depender de tu Mac)

## 1. Crear el repositorio
En https://github.com/new crea un repo **privado** llamado `agente-vuelos`.
Luego, en la terminal:

```bash
cd /Users/jnavarro/agente
git init && git add -A
git commit -m "Agente de vuelos CDMX-Madrid"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/agente-vuelos.git
git push -u origin main
```

## 2. Guardar la contraseña de aplicación como secret
En el repo: **Settings → Secrets and variables → Actions → New repository secret**

- Name: `GMAIL_APP_PASSWORD`
- Secret: la contraseña de aplicación de 16 letras (**genera una nueva**, ver abajo)

La contraseña nunca se escribe en ningún archivo del repo: el código la lee de esa
variable. Por eso `config.json` dice `"${GMAIL_APP_PASSWORD}"`.

## 3. Encenderlo
**Actions → Agente de vuelos CDMX → Madrid → Run workflow.**
Debe llegarte el primer correo en ~1 minuto. A partir de ahí corre solo cada hora.

## Costo
- Repo privado: 2,000 minutos gratis al mes. Este agente usa ~1 min por corrida,
  24 corridas al día ≈ **730 min/mes**. Entra en el plan gratuito con holgura.
- Repo público: minutos ilimitados, pero el historial de precios queda a la vista.
- Cada corrida guarda los precios en `data/`, lo que además mantiene el repo
  "activo" para que GitHub no apague el cron (lo desactiva tras 60 días sin commits).

## Ajustes
- Frecuencia: la línea `cron` en `.github/workflows/vuelos.yml`
  (`"7 */2 * * *"` = cada 2 horas, `"7,37 * * * *"` = cada 30 min).
- Objetivo de precio, tope de correos y hora del resumen: `alerts` en `config.json`.
- Los horarios del cron son **UTC**. CDMX = UTC-6.
