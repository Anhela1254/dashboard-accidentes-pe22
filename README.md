# Dashboard web PE-22 — listo para Vercel

Conversión a HTML, CSS y JavaScript del panel Tkinter del sistema de predicción de accidentes Lima–La Oroya.

## Contenido
- `public/index.html`, `public/styles.css`, `public/app.js`: interfaz web responsive y funcional.
- `public/resultados`: CSV, gráficos, GeoJSON, mapa, PDF y Excel originales.
- `public/datos`: registros y plantillas originales.
- `local_python`: código Python original para el modelo (no forma parte del sitio publicado).
- `vercel.json`: configuración de salida estática.

## Publicar desde GitHub en Vercel
1. Descomprime este ZIP.
2. Sube **el contenido de PE22_DASHBOARD_VERCEL** al repositorio GitHub (vercel.json en la raíz).
3. En Vercel, selecciona **Add New → Project**, importa tu repositorio y elige **Deploy**.
4. Preset: **Other**. Output Directory: **public** (también se configura en `vercel.json`). No hay build ni dependencias Node.
5. Tu aplicación estará en la URL de Vercel de tu proyecto.

Alternativamente, dentro del directorio con Vercel CLI ya autenticado: `vercel --prod`.

## Probar localmente
Desde la raíz: `python -m http.server 8000 -d public` y abre `http://localhost:8000`.
No abras `index.html` con doble clic porque los CSV requieren HTTP.

## Actualizar datos / entrenar
La web lee resultados publicados, pero **no reentrena ni ejecuta Tkinter en Vercel**. Para generar nuevos resultados, ejecuta el proyecto Python original localmente con las dependencias de `requirements.txt`, copia sus nuevos archivos `resultados/` a `public/resultados/` y vuelve a publicar. Para reentrenamiento online y persistencia hace falta un backend separado y almacenamiento persistente.

**Importante:** los archivos de datos publicados en `public/` serán públicamente accesibles. Revisa permisos y confidencialidad antes de desplegar.

## Aviso científico
Estimaciones exploratorias, no conteos observados de 2026. Geometría CAD/DSM y GIS aproximados; sin TPDA verificado. No afirmar causalidad ni puntos negros oficiales.
