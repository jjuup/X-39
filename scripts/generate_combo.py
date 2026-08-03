"""
Experimental PFD button data encoder/decoder.

The format is currently reverse engineered.
Generated output should always be verified
against files produced by the official
E-YOOSO X-39 software.

Repository: https://github.com/jjuup/X-39
Requires Python 3.10+
"""

import argparse
import sys
from enum import Enum
from typing import TypeAlias

# ===========================================================================
# hid  (future: x39/hid.py)
# ===========================================================================

class Key(Enum):
    """USB HID usage IDs used by the X-39 firmware."""
    # Modifiers
    CTRL = 'E0'; SHIFT = 'E1'; ALT = 'E2'; GUI = 'E3'
    # Letters
    A = '04'; B = '05'; C = '06'; D = '07'; E = '08'; F = '09'; G = '0A'; H = '0B'
    I = '0C'; J = '0D'; K = '0E'; L = '0F'; M = '10'; N = '11'; O = '12'; P = '13'
    Q = '14'; R = '15'; S = '16'; T = '17'; U = '18'; V = '19'; W = '1A'; X = '1B'
    Y = '1C'; Z = '1D'
    # Numbers
    NUM_1 = '1E'; NUM_2 = '1F'; NUM_3 = '20'; NUM_4 = '21'; NUM_5 = '22'
    NUM_6 = '23'; NUM_7 = '24'; NUM_8 = '25'; NUM_9 = '26'; NUM_0 = '27'
    # Specials
    SPACE = '2C'; ENTER = '28'; ESC = '29'; TAB = '2B'; DEL = '4C'
    # F-keys
    F1 = '3A'; F2 = '3B'; F3 = '3C'; F4 = '3D'; F5 = '3E'; F6 = '3F'
    F7 = '40'; F8 = '41'; F9 = '42'; F10 = '43'; F11 = '44'; F12 = '45'

KEY_BY_HID = {key.value: key for key in Key}

MODIFIER_ORDER = (Key.CTRL, Key.SHIFT, Key.ALT, Key.GUI)

NORMALIZE = {
    "CONTROL": "CTRL", "CMD": "GUI", "COMMAND": "GUI",
    "WINDOWS": "GUI", "WIN": "GUI", "OPTION": "ALT",
    "RETURN": "ENTER", "DELETE": "DEL", "ESCAPE": "ESC",
}

ALIASES = {
    '1': Key.NUM_1, '2': Key.NUM_2, '3': Key.NUM_3, '4': Key.NUM_4, '5': Key.NUM_5,
    '6': Key.NUM_6, '7': Key.NUM_7, '8': Key.NUM_8, '9': Key.NUM_9, '0': Key.NUM_0,
}

Shortcut: TypeAlias = str | list[Key]

# ===========================================================================
# encoder  (future: x39/encoder.py)
# ===========================================================================

def parse_shortcut(shortcut_str: str) -> list[Key]:
    """Parses 'Ctrl+Shift+Z' into a list of Key enums."""
    keys = []
    for raw in shortcut_str.split('+'):
        p = NORMALIZE.get(raw.strip().upper(), raw.strip().upper())
        if not p:
            raise ValueError("Empty key token in shortcut.")
        if p in ALIASES:
            keys.append(ALIASES[p])
        else:
            try:
                keys.append(Key[p])
            except KeyError:
                raise ValueError(f"Unknown key or typo: '{p}'")
    return keys

def validate_unique(keys: list[Key]):
    if len(set(keys)) != len(keys):
        dupes = sorted({k.name for k in keys if keys.count(k) > 1})
        raise ValueError(f"Duplicate keys are not allowed: {', '.join(dupes)}")

def validate_supported(keys: list[Key]):
    regular = [k for k in keys if k not in MODIFIER_ORDER]
    if len(regular) != 1:
        raise ValueError(f"Exactly one non-modifier key is required (found {len(regular)}).")
    if len(keys) > 4:
        raise ValueError(f"A maximum of 4 simultaneous keys is supported (found {len(keys)}).")

def sort_keys(keys: list[Key]) -> list[Key]:
    """Canonical order: CTRL, SHIFT, ALT, GUI, then the regular key."""
    modifiers = sorted((k for k in keys if k in MODIFIER_ORDER),
                       key=MODIFIER_ORDER.index)
    regular = [k for k in keys if k not in MODIFIER_ORDER]
    return modifiers + regular

def encode_button_data(shortcut: Shortcut) -> str:
    """
    Encodes a keyboard shortcut into the 128-byte ButtonAssigned_X
    payload used inside X-39 .pfd profile files.

    Supports:
      * single keys
      * modifier combinations (max 4 simultaneous keys)

    Does not support:
      * recorded macros with delays
      * mouse movement / mouse buttons
      * typed text macros
    """
    keys = parse_shortcut(shortcut) if isinstance(shortcut, str) else list(shortcut)
    validate_unique(keys)
    keys = sort_keys(keys)
    validate_supported(keys)

    events = [f"{k.value}0580" for k in keys]                 # downs
    events += [f"{k.value}0500" for k in reversed(keys)]      # ups, reversed
    payload = "".join(events)

    # Single keys mirror the keycode at the end instead of a footer byte
    if len(keys) == 1:
        return payload[:2] + "00" * 126 + payload[:2]

    payload += "00" * (127 - len(payload) // 2)               # pad to 127 bytes
    footer = sum(bytes.fromhex(payload)) % 256                # informational
    return payload + f"{footer:02X}"

# ===========================================================================
# decoder  (future: x39/decoder.py)
# ===========================================================================

def _events(hex_string: str):
    for i in range(0, 252, 6):
        chunk = hex_string[i:i + 6]
        if chunk == "000000":
            break
        yield chunk

def decode_button_data(hex_string: str, verify: bool = True) -> str:
    """
    Inspects a 256-char ButtonAssigned_X block and returns the shortcut.
    With verify=True, rejects unbalanced press/release sequences
    (useful for detecting corrupted .pfd data).
    """
    if len(hex_string) != 256:
        raise ValueError("Invalid PFD block: expected 256 hex characters.")
    hex_string = hex_string.upper()

    # Single-key mirror format
    if hex_string[2:254] == "00" * 126 and hex_string[254:] == hex_string[:2]:
        key = KEY_BY_HID.get(hex_string[:2])
        return key.name if key else f"UNKNOWN_KEY({hex_string[:2]})"

    downs, ups = [], []
    for chunk in _events(hex_string):
        keycode, flag = chunk[:2], chunk[4:6]
        if flag == "80":
            downs.append(keycode)
        elif flag == "00":
            ups.append(keycode)
        else:
            raise ValueError(f"Unknown event flag 0x{flag}.")

    if verify and downs[::-1] != ups:
        raise ValueError("Unbalanced press/release sequence; block may be corrupted.")

    names = [KEY_BY_HID.get(h, f"0x{h}") for h in downs]
    names = [n.name if isinstance(n, Key) else n for n in names]
    return "+".join(names) if names else "UNASSIGNED"

def footer_info(hex_string: str) -> tuple[int, int]:
    """(recomputed footer, stored footer) — informational only."""
    return (sum(bytes.fromhex(hex_string[:254])) % 256,
            int(hex_string[254:], 16))

# ===========================================================================
# cli  (future: x39/cli.py)
# ===========================================================================

def _is_hex_block(s: str) -> bool:
    return len(s) == 256 and all(c in "0123456789abcdefABCDEF" for c in s)

def _cmd_encode(shortcut: str):
    keys = sort_keys(parse_shortcut(shortcut))
    validate_unique(keys)
    validate_supported(keys)
    print(f"Shortcut  : {shortcut}")
    print(f"Normalized: {'+'.join(k.name for k in keys)}\n")
    print("Events")
    for k in keys:            print(f"{k.value} 05 80   {k.name} down")
    for k in reversed(keys):  print(f"{k.value} 05 00   {k.name} up")
    block = encode_button_data(keys)
    print(f"\nFooter    : 0x{block[-2:]}\n")
    print("256-char PFD block")
    print(block)
    print(f"\nVerify    : decodes back to {decode_button_data(block)}")

def _cmd_decode(hex_string: str):
    hex_string = hex_string.upper()
    print("Events")
    for chunk in _events(hex_string):
        k = KEY_BY_HID.get(chunk[:2])
        label = k.name if k else f"0x{chunk[:2]}"
        print(f"{chunk[:2]} {chunk[2:4]} {chunk[4:6]}   {label} "
              f"{'down' if chunk[4:6] == '80' else 'up'}")
    rec, stored = footer_info(hex_string)
    match = "matches" if rec == stored else "MISMATCH"
    print(f"\nFooter    : 0x{stored:02X} (recomputed 0x{rec:02X} — {match}, informational)")
    print(f"Shortcut  : {decode_button_data(hex_string)}")

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("encode", "decode", "-h", "--help"):
        argv = [("decode" if _is_hex_block(argv[0]) else "encode")] + argv

    parser = argparse.ArgumentParser(
        prog="combo.py",
        description="Experimental X-39 PFD combo encoder/decoder.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_enc = sub.add_parser("encode", help="shortcut -> 256-char PFD block")
    p_enc.add_argument("shortcut", help='e.g. "Ctrl+Shift+Z"')
    p_dec = sub.add_parser("decode", help="256-char PFD block -> shortcut")
    p_dec.add_argument("hexstring", help="256 hex characters")
    args = parser.parse_args(argv)

    try:
        if args.command == "encode":
            _cmd_encode(args.shortcut)
        else:
            _cmd_decode(args.hexstring)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
