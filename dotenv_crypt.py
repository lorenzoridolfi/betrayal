"""Helpers to encrypt dotenv files and inject decrypted values into environment."""

import os
import io
from cryptography.fernet import Fernet
from dotenv import dotenv_values


class DotenvVault:
    """Manage Fernet key material and encrypted dotenv payloads."""

    def __init__(self, key_path: str) -> None:
        """Initialize the vault with the filesystem path to key material."""
        self.key_path = key_path

    def generate_key(self) -> None:
        """Generate and persist a new Fernet key."""
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        with open(self.key_path, "wb") as key_file:
            key_file.write(key)
        print(f"✅ Chave gerada com sucesso em: {self.key_path}")

    def encrypt_dotenv(
        self, source_path: str = ".env", dest_path: str = ".env.enc"
    ) -> None:
        """Encrypt a plaintext dotenv file into an encrypted payload file."""
        with open(self.key_path, "rb") as key_file:
            key = key_file.read()

        fernet = Fernet(key)
        with open(source_path, "rb") as f:
            data = f.read()

        encrypted_data = fernet.encrypt(data)
        with open(dest_path, "wb") as f:
            f.write(encrypted_data)
        print(f"🔒 Arquivo {source_path} criptografado para {dest_path}")

    def load_to_environ(self, enc_env_path: str = ".env.enc") -> None:
        """Decrypt dotenv payload and inject key-value pairs into environment."""
        with open(self.key_path, "rb") as key_file:
            key = key_file.read()

        fernet = Fernet(key)
        with open(enc_env_path, "rb") as f:
            encrypted_content = f.read()

        # Keep decrypted content in memory; never write temporary plaintext files.
        decrypted_data = fernet.decrypt(encrypted_content).decode()

        # Parse dotenv key/value text from in-memory stream.
        config = dotenv_values(stream=io.StringIO(decrypted_data))

        # Inject explicit values only; ignore empty entries.
        for key, value in config.items():
            if value is not None:
                os.environ[key] = value

        print(f"🚀 {len(config)} variáveis carregadas no os.environ.")


# --- EXEMPLO DE USO ---
if __name__ == "__main__":
    # 1. Defina um caminho fora da pasta do seu projeto (Ex: Home do usuário)
    MINHA_CHAVE_MESTRA = os.path.expanduser("~/.meus_segredos/ai_project.key")

    vault = DotenvVault(MINHA_CHAVE_MESTRA)

    # PASSO A (Só rodar uma vez na vida):
    # vault.generate_key()
    # vault.encrypt_dotenv(".env") # Cria o .env.enc

    # PASSO B (No topo do seu arquivo main.py):
    vault.load_to_environ(".env.enc")

    # Teste:
    import os

    print(f"Minha chave de AI é: {os.getenv('OPENAI_API_KEY')}")
