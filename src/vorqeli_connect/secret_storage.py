"""Encrypt the Telegram secret with Windows DPAPI, bound to the current account.

Only the Windows branch performs encryption. Source/test runs on other systems
continue to use the original format for developer portability. This module
never sends the secret to the network.
"""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _blob(content: bytes):
    buffer = ctypes.create_string_buffer(content)
    return _DataBlob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi(content: bytes, *, encrypt: bool) -> bytes:
    if os.name != 'nt':
        raise OSError('DPAPI available only on Windows')
    crypt = ctypes.windll.crypt32
    kernel = ctypes.windll.kernel32
    input_blob, owned_buffer = _blob(content)
    output_blob = _DataBlob()
    if encrypt:
        func = crypt.CryptProtectData
        # Suppress UI prompts. DPAPI uses the current Windows user account.
        args = (ctypes.byref(input_blob), None, None, None, None, 0x01,
                ctypes.byref(output_blob))
    else:
        func = crypt.CryptUnprotectData
        args = (ctypes.byref(input_blob), None, None, None, None, 0x01,
                ctypes.byref(output_blob))
    func.restype = wintypes.BOOL
    if not func(*args):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel.LocalFree.argtypes = (ctypes.c_void_p,)
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def protect(secret: str) -> str:
    if not isinstance(secret, str):
        raise ValueError('Invalid secret type')
    return base64.b64encode(_dpapi(secret.encode('ascii'), encrypt=True)).decode('ascii')


def unprotect(encoded: str) -> str:
    if not isinstance(encoded, str) or len(encoded) > 16384:
        raise ValueError('Invalid protected secret')
    try:
        payload = base64.b64decode(encoded, validate=True)
        if not payload:
            raise ValueError('Empty encrypted secret')
        return _dpapi(payload, encrypt=False).decode('ascii')
    except (UnicodeError, ValueError) as exc:
        raise ValueError('Invalid protected secret encoding') from exc


def serialize_secret(secret: str) -> dict[str, str]:
    """Fail closed on Windows; never fall back to plaintext when DPAPI fails."""
    if not secret:
        return {'telegram_secret': ''}
    if os.name == 'nt':
        return {'telegram_secret_dpapi': protect(secret)}
    return {'telegram_secret': secret}


def deserialize_secret(data: dict) -> str:
    if os.name == 'nt' and data.get('telegram_secret_dpapi'):
        return unprotect(data['telegram_secret_dpapi'])
    # Legacy migration: old v0.14 configs are still readable until next save.
    return data.get('telegram_secret', '')
