from emmett_core.cryptography.symmetric import decrypt_b64, decrypt_hex, encrypt_b64, encrypt_hex


text = b"plain text"
key = "some key"


def test_b64():
    ct = encrypt_b64(text, key)
    assert decrypt_b64(ct, key) == text


def test_hex():
    ct = encrypt_hex(text, key)
    assert decrypt_hex(ct, key) == text
