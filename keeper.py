import os
import sys
import time
import random
import datetime
import urllib.request
import json
import oci

def log(msg):
    now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{now}] {msg}", flush=True)

def set_github_output(name, value):
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        try:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(f"{name}={value}\n")
        except Exception:
            pass

def notify_telegram(token, chat_id, message):
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        )
        urllib.request.urlopen(req, timeout=10)
        log("Notificacion enviada a Telegram correctamente.")
    except Exception:
        log("No se pudo enviar notificacion a Telegram.")

def notify_webhook(webhook_url, message):
    if not webhook_url:
        return
    try:
        data = json.dumps({"content": message, "text": message}).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        )
        urllib.request.urlopen(req, timeout=10)
        log("Notificacion enviada al webhook correctamente.")
    except Exception as err:
        log(f"No se pudo enviar webhook: {err}")

def main():
    log("=== HALCONFLOWS OCI ALWAYS FREE KEEPER (GITHUB ACTIONS 24/7) ===")
    
    # 1. Validar variables de entorno requeridas
    required_envs = [
        "OCI_USER_OCID", "OCI_FINGERPRINT", "OCI_TENANCY_OCID", 
        "OCI_KEY_CONTENT", "OCI_REGION", "OCI_AD", 
        "OCI_BOOT_VOLUME_ID", "OCI_SUBNET_ID", "OCI_SSH_PUBLIC_KEY"
    ]
    for k in required_envs:
        if not os.environ.get(k):
            log(f"ERROR: Variable de entorno faltante: {k}")
            sys.exit(1)

    key_content = os.environ["OCI_KEY_CONTENT"].strip()
    if "\\n" in key_content:
        key_content = key_content.replace("\\n", "\n")

    config = {
        "user": os.environ["OCI_USER_OCID"],
        "fingerprint": os.environ["OCI_FINGERPRINT"],
        "tenancy": os.environ["OCI_TENANCY_OCID"],
        "key_content": key_content,
        "region": os.environ["OCI_REGION"]
    }

    try:
        oci.config.validate_config(config)
    except Exception as e:
        log(f"Error de validacion en configuracion OCI: {e}")
        sys.exit(1)

    compute_client = oci.core.ComputeClient(config)
    network_client = oci.core.VirtualNetworkClient(config)

    compartment_id = config["tenancy"]
    ad = os.environ["OCI_AD"]
    boot_volume_id = os.environ["OCI_BOOT_VOLUME_ID"]
    subnet_id = os.environ["OCI_SUBNET_ID"]
    ssh_key = os.environ["OCI_SSH_PUBLIC_KEY"].strip()
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    # 2. Verificar si la instancia ya existe
    log("Verificando si la instancia solarsail ya se encuentra activa...")
    try:
        instances = compute_client.list_instances(
            compartment_id=compartment_id,
            display_name="solarsail"
        ).data
        active = [i for i in instances if i.lifecycle_state in ["RUNNING", "PROVISIONING", "STARTING"]]
        if active:
            inst = active[0]
            log(f"LA INSTANCIA YA EXISTE Y ESTA EN ESTADO: {inst.lifecycle_state} (OCID: {inst.id})")
            notify_telegram(
                telegram_token, 
                telegram_chat_id, 
                f"🎉 *¡Servidor Solarsail ya activo!*\nEstado: `{inst.lifecycle_state}`\nID: `{inst.id}`"
            )
            notify_webhook(webhook_url, f"🎉 ¡Tu servidor Solarsail en Oracle Cloud ya está activo ({inst.lifecycle_state})!")
            set_github_output("instance_created", "true")
            return 0
    except Exception as e:
        log(f"Aviso al listar instancias: {e}")

    # 3. Bucle de caceria con duracion maxima de 5 horas por workflow
    max_duration_seconds = int(os.environ.get("MAX_RUN_SECONDS", 18000)) # 5 horas
    start_time = time.time()
    attempt = 1

    log(f"Iniciando caceria continua en {ad} (2 OCPUs / 12 GB RAM / 200 GB Boot Volume)...")

    shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=2.0,
        memory_in_gbs=12.0
    )

    source_details = oci.core.models.InstanceSourceViaBootVolumeDetails(
        boot_volume_id=boot_volume_id
    )

    create_vnic_details = oci.core.models.CreateVnicDetails(
        subnet_id=subnet_id,
        assign_public_ip=True
    )

    instance_details = oci.core.models.LaunchInstanceDetails(
        availability_domain=ad,
        compartment_id=compartment_id,
        display_name="solarsail",
        shape="VM.Standard.A1.Flex",
        shape_config=shape_config,
        source_details=source_details,
        create_vnic_details=create_vnic_details,
        metadata={"ssh_authorized_keys": ssh_key}
    )

    while True:
        elapsed = time.time() - start_time
        if elapsed > max_duration_seconds:
            log(f"Limite de sesion alcanzado ({int(elapsed/60)} mins). Terminando para ceder el turno al siguiente ciclo...")
            set_github_output("instance_created", "false")
            return 0

        log(f"Intento #{attempt} - Solicitando capacidad en {ad}...")

        try:
            res = compute_client.launch_instance(instance_details)
            instance = res.data
            log("="*60)
            log("¡¡¡EXITO TOTAL!!! INSTANCIA CREADA EN ORACLE CLOUD")
            log(f"ID: {instance.id}")
            log(f"Estado: {instance.lifecycle_state}")
            log("="*60)
            
            # Obtener IP publica
            public_ip = "Asignando..."
            time.sleep(10)
            try:
                vnic_attachments = compute_client.list_vnic_attachments(
                    compartment_id=compartment_id,
                    instance_id=instance.id
                ).data
                if vnic_attachments:
                    vnic = network_client.get_vnic(vnic_attachments[0].vnic_id).data
                    public_ip = vnic.public_ip
                    log(f"IP Publica Asignada: {public_ip}")
            except Exception as vnic_err:
                log(f"Error consultando IP: {vnic_err}")

            success_msg = (
                f"🚨 *¡ÉXITO TOTAL! Servidor Creado en Oracle Cloud*\n\n"
                f"🖥️ *Instancia:* `solarsail` (2 OCPUs / 12 GB RAM)\n"
                f"💾 *Disco:* 200 GB Boot Volume (Datos intactos)\n"
                f"🌐 *IP Pública:* `{public_ip}`\n"
                f"⚡ *Estado:* `{instance.lifecycle_state}`\n"
                f"📍 *Zona:* `{ad}`"
            )
            notify_telegram(telegram_token, telegram_chat_id, success_msg)
            notify_webhook(webhook_url, f"🚨 ¡ÉXITO! Tu servidor Solarsail en Oracle Cloud ha sido aprovisionado.\nIP Pública: `{public_ip}`\nEstado: `{instance.lifecycle_state}`")
            set_github_output("instance_created", "true")
            return 0

        except oci.exceptions.ServiceError as se:
            status = se.status
            code = se.code
            message = se.message

            if status == 500 or "Out of host capacity" in message or "out of capacity" in message.lower():
                wait = random.randint(5, 9)
                log(f"Sin cupo en este milisegundo (500 Out of host capacity). Reintentando en {wait}s...")
                time.sleep(wait)
            elif status == 429 or "TooManyRequests" in code:
                log("Tasa de peticiones alcanzada (429). Pausando 45 segundos de seguridad...")
                time.sleep(45)
            elif status == 400 and "LimitExceeded" in code:
                log("Aviso de cuota/limite (400 LimitExceeded). Reintentando en 30s...")
                time.sleep(30)
            elif status in [502, 503, 504]:
                log(f"Aviso de puerta de enlace OCI ({status}). Reintentando en 10s...")
                time.sleep(10)
            else:
                log(f"Respuesta OCI ({status} {code}): {message}. Reintentando en 10s...")
                time.sleep(10)

        except Exception as ex:
            log(f"Error imprevisto en la solicitud: {ex}. Reintentando en 10s...")
            time.sleep(10)

        attempt += 1

if __name__ == "__main__":
    sys.exit(main())
