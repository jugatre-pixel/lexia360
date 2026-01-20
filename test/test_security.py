from core import security

def test_password_hash_and_verify():
    pw = "a_secure_password_123"
    hashed = security.get_password_hash(pw)
    assert security.verify_password(pw, hashed)

def test_token_roundtrip():
    token = security.create_access_token("test@example.com")
    email = security.decode_token(token)
    assert email == "test@example.com"
