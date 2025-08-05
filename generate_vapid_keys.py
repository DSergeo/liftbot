
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

# Генерація приватного ключа
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

# Отримання публічного ключа в DER форматі (ASN.1)
public_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)

# Отримання приватного ключа в PEM форматі
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# Отримання публічного ключа для клієнта (base64 URL safe)
vapid_public_base64 = base64.urlsafe_b64encode(public_bytes).decode("utf-8").rstrip("=")

print("🔐 VAPID PRIVATE KEY (PEM, для сервера):")
print(private_pem.decode())

print("\n📢 VAPID PUBLIC KEY (Base64, для клієнта):")
print(vapid_public_base64)
