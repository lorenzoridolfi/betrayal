import os
import io
from cryptography.fernet import Fernet
from dotenv import dotenv_values

class DotenvVault:
    def __init__(self, key_path):
        self.key_path = key_path

    def generate_key(self):
        """Gera uma chave e salva no local seguro fora do projeto."""
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        with open(self.key_path, "wb") as key_file:
            key_file.write(key)
        print(f"✅ Chave gerada com sucesso em: {self.key_path}")

    def encrypt_dotenv(self, source_path=".env", dest_path=".env.enc"):
        """Criptografa o arquivo .env original."""
        with open(self.key_path, "rb") as key_file:
            key = key_file.read()
        
        fernet = Fernet(key)
        with open(source_path, "rb") as f:
            data = f.read()
        
        encrypted_data = fernet.encrypt(data)
        with open(dest_path, "wb") as f:
            f.write(encrypted_data)
        print(f"🔒 Arquivo {source_path} criptografado para {dest_path}")

    def load_to_environ(self, enc_env_path=".env.enc"):
        """Descriptografa e injeta no os.environ (Variáveis de Ambiente)."""
        with open(self.key_path, "rb") as key_file:
            key = key_file.read()
        
        fernet = Fernet(key)
        with open(enc_env_path, "rb") as f:
            encrypted_content = f.read()
        
        # Descriptografa e converte para string
        decrypted_data = fernet.decrypt(encrypted_content).decode()
        
        # Usa o dotenv_values para parsear a string sem criar arquivo físico
        config = dotenv_values(stream=io.StringIO(decrypted_data))
        
        # Injeta opcionalmente no ambiente do Sistema Operacional
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
