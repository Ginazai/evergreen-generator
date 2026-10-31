# CI/CD y despliegue en Render

```
PR ──► CI (lint · imagen+tests+smoke · audit) ──► merge a main
main ──► CI ✓ ──► CD: publica ghcr.io/<repo>:sha-xxxxxxx ──► staging (Render, automático)
      ──► abre/actualiza PR "Promote production to sha-xxxxxxx"
tú revisas y apruebas ese PR ──► merge ──► deploy-production.yml verifica la aprobación ──► producción + 5 min de vigilancia
```

Nada llega a producción sin un PR aprobado por otra persona. Rollback: *Actions → CD → Run workflow* con `image_tag` = un `sha-xxxxxxx` anterior (abre un PR de rollback por el mismo camino).

## ⚠️ Antes de exponerlo en internet

- **La GUI no tiene login.** Quien conozca la URL puede usarla, gastar tu cuota de Gemini/Cloudflare y cambiar las claves guardadas. Ponle autenticación o un proxy con acceso restringido (Cloudflare Access, Tailscale, etc.) antes de usarla en serio.
- **Sin disco no hay datos.** Render borra el sistema de archivos en cada deploy/reinicio. Producción usa un disco (`render.yaml`), que exige una instancia de pago, permite una sola instancia y corta el servicio unos segundos por deploy. Staging va en `free` sin disco.
- El plan `starter` (512 MB) puede quedarse corto con ffmpeg/Piper; si ves reinicios por memoria, sube de plan.

## Configuración (una vez)

1. **Repo → Settings → Actions → General → Workflow permissions**: *Read and write* + activar *Allow GitHub Actions to create and approve pull requests*.
2. **Branch protection en `main`** (si tu plan lo permite): exigir PR, 1 aprobación y el check **CI gate** (es el único check requerido; sumar jobs no obliga a tocar la protección).
3. **Primer push a `main`**: CI corre y CD publica la imagen en GHCR. El job *Staging* fallará (aún no hay servicio): es esperado.
4. **Render**: edita `render.yaml` (`OWNER/REPO` en minúsculas, credenciales si el paquete es privado: Render → Account Settings → Registry Credentials, PAT con `read:packages`) y crea el Blueprint. Crea dos servicios: `evergreen-staging` y `evergreen-production`.
5. En cada servicio de Render: **Settings → Deploy Hook** → copia la URL.
6. **GitHub → Settings → Environments**: crea `staging` y `production`. En cada uno:
   - Secret `RENDER_DEPLOY_HOOK` = la URL del paso 5 (es un secreto: nunca la pegues en logs ni PRs).
   - Variable `APP_URL` = `https://<servicio>.onrender.com` (activa el health check posterior).
7. Reejecuta el job fallido de CD (*Re-run failed jobs*). Staging despliega y se abre el primer PR de promoción; apruébalo (otra cuenta distinta del autor) y haz merge.

## Cosas que conviene saber

- Render no se redespliega solo: el pipeline llama al Deploy Hook con `imgURL` (el tag exacto). No uses el botón *Deploy* de Render para producción: ese saca `:latest`, que puede ser un build que aún no aprobaste.
- Las claves de Gemini/Cloudflare se guardan desde la propia GUI en `settings.env` dentro del disco; no hace falta ponerlas como variables en Render.
- Si no quieres staging: en `cd.yml` borra el job `staging`, quita `staging` de `needs` en `promote` y borra la línea `(needs.staging.result == 'success' || github.event_name == 'workflow_dispatch') &&` de su `if`.
- La cobertura mínima (85 %) vive en `pyproject.toml`; el job de imagen ejecuta `pytest` dentro de la imagen para que los tests de ffmpeg no se salten.
- CI instala dependencias solo desde `requirements-ci.txt` (con hashes, `--only-binary`). Si cambias `pyproject.toml`, regenera el lock con el comando de la cabecera de `requirements-ci.in`; Dependabot también lo actualiza.
