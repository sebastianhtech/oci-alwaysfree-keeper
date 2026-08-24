# OCI Always Free Instance Keeper 24/7 (GitHub Actions)

Automatización de alta disponibilidad en la nube para aprovisionar instancias Always Free ARM (`VM.Standard.A1.Flex`, 2 OCPUs, 12 GB RAM) asociando el volumen de arranque persistente (`solarsail`, 200 GB) en Oracle Cloud Infrastructure (región `us-ashburn-1`, AD-2).

## Características
* Ejecución ininterrumpida 24/7/365 en runners de GitHub Actions.
* Cero dependencia de laptops o servidores locales.
* Jitter aleatorio controlado y pausas de seguridad ante `429 Too Many Requests`.
* Notificación instantánea vía Webhook cuando la máquina es aprovisionada.
