#!/usr/bin/env python3
"""
Samsung Engineering Mode Token Generator
============================================

Token format: ENGRSS0002 (Format B for installToken)
INTE section: signature(256) + device_cert + root_ca_cert

Usage:
  python engmode.py generate \
    --dev-key my_dev.key \
    --dev-cert my_dev.der \
    --root-cert my_root.der \
    -o token.bin

  python engmode.py analyze -i token.bin
"""

import struct
import sys
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

try:
    from Crypto.PublicKey import RSA
    from Crypto.Signature import PKCS1_v1_5
    from Crypto.Hash import SHA256
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    print("[WARN] pycryptodome not installed. pip install pycryptodome")

# ══════════════════════════════════════════════════════════════════════════
# BINARY BUILDERS
# ══════════════════════════════════════════════════════════════════════════

def pad(data: bytes, size: int) -> bytes:
    return (data + b'\x00' * size)[:size]

def build_tlv(items: list) -> bytes:
    """Build TLV entries: [(type_u16, value_bytes), ...]"""
    blob = b''
    for t, v in items:
        blob += struct.pack('<HH', t, len(v))
        blob += v
    return blob

def build_section(magic: bytes, items: list) -> bytes:
    """Section: magic(4) + size(4) + count(4) + TLV data"""
    tlv = build_tlv(items)
    return magic + struct.pack('<II', len(tlv), len(items)) + tlv

def build_raw_section(magic: bytes, data: bytes, count: int) -> bytes:
    """Section with raw data blob"""
    return magic + struct.pack('<II', len(data), count) + data

# ══════════════════════════════════════════════════════════════════════════
# MODE / GROUP ENTRIES
# ══════════════════════════════════════════════════════════════════════════

def build_mode_entry(index, name, desc, group=0):
    """MODB entry: short + char[32] + char[128] + short + int + int + attrs"""
    entry = struct.pack('<H', index)
    entry += pad(name, 32)
    entry += pad(desc, 128)
    entry += struct.pack('<H', group)
    # Minimal attr: type=1, len=0
    attr = struct.pack('<HH', 1, 0)
    entry += struct.pack('<iI', len(attr), 1)
    entry += attr
    return entry

def build_group_entry(index, name, desc):
    """GRDB entry: short + char[32] + char[128] + int + int + attrs"""
    entry = struct.pack('<H', index)
    entry += pad(name, 32)
    entry += pad(desc, 128)
    attr = struct.pack('<HH', 1, 0)
    entry += struct.pack('<iI', len(attr), 1)
    entry += attr
    return entry

# ══════════════════════════════════════════════════════════════════════════
# REAL MODE DEFINITIONS — from actual Samsung tokens
# ══════════════════════════════════════════════════════════════════════════

REAL_MODES = [
    (1, b'MODE_FACTORY_BIN',    b'Allow flashing of Factory firmware'),
    (2, b'MODE_ATCMD',          b'Enable CP Engineer commands'),
]

REAL_GROUPS = [
    (0, b'GRDB', b'Binary Flashing Allow to flash'),
]

# ══════════════════════════════════════════════════════════════════════════
# CRYPTO
# ══════════════════════════════════════════════════════════════════════════

def sign_data(data: bytes, key_pem: bytes) -> bytes:
    """PKCS#1 v1.5 SHA-256 signature"""
    if not HAS_CRYPTO:
        return b'\x00' * 256
    key = RSA.import_key(key_pem)
    h = SHA256.new(data)
    return PKCS1_v1_5.new(key).sign(h)

# ══════════════════════════════════════════════════════════════════════════
# TOKEN BUILDER
# ══════════════════════════════════════════════════════════════════════════

def build_token(
    token_id=b'1A2B3C4D5E6F7890',
    model_name=b'SM-S918B',
    did=b'2004376D249F2911',
    imei=b'R5CWAXXXXX',
    single_id=b'DASEUL',
    otp=b'000000',
    nonce=b'\x00' * 32,
    issued_date=b'20250529',
    expiry_date=b'20251231',
    dev_key_pem=None,
    dev_cert_der=None,
    root_cert_der=None,
    version=b'0002',
    header_type=b'RSS',
):
    """
    Build Format B token for installToken.
    
    Cert chain: root CA -> device cert -> token signature
    Sign token body with device key.
    INTE = [signature] + [device_cert + root_ca_cert]
    """

    # ── Sections ──
    toke = build_section(b'TOKE', [
        (1, pad(token_id, 16)),
        (2, struct.pack('<H', 1)),       # device_unique_info
        (3, struct.pack('<H', 1)),       # num_of_devices
    ])

    devi = build_section(b'DEVI', [
        (1, pad(model_name, 16)),
        (2, pad(did, 16)),
        (3, pad(imei, 15)),
    ])

    issu = build_section(b'ISSU', [
        (1, pad(single_id, 24)),
    ])

    # MODE — simple index list
    mode_data = b''
    mode_indices = [1, 2]
    for idx in mode_indices:
        mode_data += struct.pack('<HH', idx, 0)
    mode_section = b'MODE' + struct.pack('<II', len(mode_data), len(mode_indices)) + mode_data

    vali = build_section(b'VALI', [
        (1, pad(issued_date, 8)),
        (2, pad(expiry_date, 8)),
    ])

    # MODB
    mode_entries = b''
    for idx, name, desc in REAL_MODES:
        mode_entries += build_mode_entry(idx, name, desc)
    modb = build_raw_section(b'MODB', mode_entries, len(REAL_MODES))

    # GRDB
    group_entries = b''
    for idx, name, desc in REAL_GROUPS:
        group_entries += build_group_entry(idx, name, desc)
    grdb = build_raw_section(b'GRDB', group_entries, len(REAL_GROUPS))

    # ── Calculate layout ──
    # Header: prefix(10) + headerLen(4) + 8 pointers(32)
    prefix = b'ENG' + header_type + version
    header_size = 4 + (8 * 4)  # headerLen field + 8 pointers
    data_start = len(prefix) + header_size  # = 10 + 36 = 46

    # Data order: TOKE DEVI ISSU MODE VALI MODB GRDB INTE
    off_toke = data_start
    off_devi = off_toke + len(toke)
    off_issu = off_devi + len(devi)
    off_mode = off_issu + len(issu)
    off_vali = off_mode + len(mode_section)
    off_modb = off_vali + len(vali)
    off_grdb = off_modb + len(modb)
    off_inte = off_grdb + len(grdb)

    # Build header
    header = prefix
    header += struct.pack('<I', header_size)
    header += struct.pack('<I', off_toke)
    header += struct.pack('<I', off_devi)
    header += struct.pack('<I', off_issu)
    header += struct.pack('<I', off_mode)
    header += struct.pack('<I', off_vali)
    header += struct.pack('<I', off_modb)
    header += struct.pack('<I', off_grdb)
    header += struct.pack('<I', off_inte)

    # Body without INTE
    body = header + toke + devi + issu + mode_section + vali + modb + grdb

    assert len(body) == off_inte, f"Body length {len(body)} != off_inte {off_inte}"

    # ── Sign and build INTE ──
    if dev_key_pem and dev_cert_der:
        signature = sign_data(body, dev_key_pem)
    else:
        signature = b'\x00' * 256

    # Cert blob: device cert + root CA cert concatenated
    cert_blob = b''
    if dev_cert_der:
        cert_blob += dev_cert_der
    if root_cert_der:
        cert_blob += root_cert_der

    if not cert_blob:
        cert_blob = b'\x00' * 256

    inte = build_section(b'INTE', [
        (1, signature),
        (2, cert_blob),
    ])

    token = body + inte

    print(f"Token size: {len(token)} bytes")
    print(f"Header: {prefix.decode()}")
    print(f"Sections: TOKE@{off_toke} DEVI@{off_devi} ISSU@{off_issu} "
          f"MODE@{off_mode} VALI@{off_vali} MODB@{off_modb} GRDB@{off_grdb} INTE@{off_inte}")
    print(f"Signed region: 0-{off_inte} ({off_inte} bytes)")
    print(f"Signature: {len(signature)} bytes")
    print(f"Cert blob: {len(cert_blob)} bytes")

    return token

# ══════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════════════════════════

def analyze(data):
    """Parse and display token structure"""
    if len(data) < 46:
        print("Too short")
        return

    prefix = data[:10].decode('ascii', errors='replace')
    print(f"Header: {prefix}")
    print(f"Size: {len(data)} bytes")
    print(f"SHA-256: {hashlib.sha256(data).hexdigest()}")

    if data[:3] != b'ENG':
        print("Not an ENG token")
        return

    off = 10
    hdr_len = struct.unpack_from('<I', data, off)[0]; off += 4
    print(f"Header data size: {hdr_len}")

    names = ['TOKE', 'DEVI', 'ISSU', 'MODE', 'VALI', 'INTE', 'MODB', 'GRDB']
    for name in names:
        if off + 4 <= len(data):
            ptr = struct.unpack_from('<I', data, off)[0]; off += 4
            actual = data[ptr:ptr+4].decode('ascii', errors='replace') if ptr+4 <= len(data) else '???'
            match = '✓' if actual == name else f'✗ got {actual}'
            
            # Parse section header
            if ptr + 12 <= len(data) and actual == name:
                sec_size = struct.unpack_from('<I', data, ptr+4)[0]
                sec_count = struct.unpack_from('<I', data, ptr+8)[0]
                print(f"  {name} @ {ptr:4d} (0x{ptr:04x}) size={sec_size:5d} count={sec_count} {match}")
                
                # Show TLV entries for interesting sections
                if name in ('TOKE', 'DEVI', 'ISSU', 'VALI', 'INTE'):
                    tpos = ptr + 12
                    for i in range(sec_count):
                        if tpos + 4 > len(data):
                            break
                        t = struct.unpack_from('<H', data, tpos)[0]
                        l = struct.unpack_from('<H', data, tpos+2)[0]
                        v = data[tpos+4:tpos+4+l]
                        # Try ascii
                        try:
                            vstr = v.decode('ascii')
                            if all(32 <= ord(c) < 127 for c in vstr):
                                print(f"       tag={t} len={l}: \"{vstr}\"")
                            else:
                                raise ValueError
                        except:
                            print(f"       tag={t} len={l}: {v[:32].hex()}{'...' if l > 32 else ''}")
                        tpos += 4 + l
            else:
                print(f"  {name} @ {ptr:4d} (0x{ptr:04x}) {match}")

# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description='Samsung EM Token Generator')
    sub = p.add_subparsers(dest='cmd')

    gen = sub.add_parser('generate')
    gen.add_argument('--token-id', default='1A2B3C4D5E6F7890')
    gen.add_argument('--model', default='SM-S999U')
    gen.add_argument('--did', default='1234567890ABCDEF')
    gen.add_argument('--imei', default='FEDCBA0987654321')
    gen.add_argument('--single-id', default='DASEUL')
    gen.add_argument('--issued', default='20250529')
    gen.add_argument('--expiry', default='20251231')
    gen.add_argument('--dev-key', help='Device RSA private key PEM')
    gen.add_argument('--dev-cert', help='Device certificate DER')
    gen.add_argument('--root-cert', help='Root CA certificate DER')
    gen.add_argument('-o', '--output', default='token.bin')

    ana = sub.add_parser('analyze')
    ana.add_argument('-i', '--input', required=True)

    args = p.parse_args()

    if args.cmd == 'generate':
        dev_key = None
        dev_cert = None
        root_cert = None

        if args.dev_key:
            dev_key = Path(args.dev_key).read_bytes()
        if args.dev_cert:
            dev_cert = Path(args.dev_cert).read_bytes()
        if args.root_cert:
            root_cert = Path(args.root_cert).read_bytes()

        token = build_token(
            token_id=args.token_id.encode(),
            model_name=args.model.encode(),
            did=args.did.encode(),
            imei=args.imei.encode(),
            single_id=args.single_id.encode(),
            issued_date=args.issued.encode(),
            expiry_date=args.expiry.encode(),
            dev_key_pem=dev_key,
            dev_cert_der=dev_cert,
            root_cert_der=root_cert,
        )

        Path(args.output).write_bytes(token)
        print(f"\nWritten: {args.output}")

        # Verify
        print("\n── Verify ──")
        analyze(token)

    elif args.cmd == 'analyze':
        data = Path(args.input).read_bytes()
        analyze(data)

    else:
        p.print_help()

if __name__ == '__main__':
    main()
