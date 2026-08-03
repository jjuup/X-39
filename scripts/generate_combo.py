"""
Experimental PFD combo encoder.

The format is currently reverse engineered.
Generated output should always be verified
against files produced by the official
E-YOOSO X-39 software.

Repository: https://github.com/jjuup/X-39
"""

from enum import Enum

class Key(Enum):
    """Internal representation of USB HID Usage IDs."""
    # Modifiers
    CTRL = 'E0'
    SHIFT = 'E1'
    ALT = 'E2'
    GUI = 'E3'
    
    # Letters
    A = '04'; B = '05'; C = '06'; D = '07'; E = '08'; F = '09'; G = '0A'; H = '0B'
    I = '0C'; J = '0D'; K = '0E'; L = '0F'; M = '10'; N = '11'; O = '12'; P = '13'
    Q = '14'; R = '15'; S = '16'; T = '17'; U = '18'; V = '19'; W = '1A'; X = '1B'
    Y = '1C'; Z = '1D'
    
    # Numbers
    NUM_1 = '1E'; NUM_2 = '1F'; NUM_3 = '20'; NUM_4 = '21'; NUM_5 = '22'
    NUM_6 = '23'; NUM_7 = '24'; NUM_8 = '25'; NUM_9 = '26'; NUM_0 = '27'
    
    # Specials
    SPACE = '2C'
    ENTER = '28'
    ESC = '29'
    TAB = '2B'
    DEL = '4C'
    
    # F-Keys
    F1 = '3A'; F2 = '3B'; F3 = '3C'; F4 = '3D'; F5 = '3E'; F6 = '3F'
    F7 = '40'; F8 = '41'; F9 = '42'; F10 = '43'; F11 = '44'; F12 = '45'

# Map string aliases to Keys for the parser
ALIASES = {
    '1': Key.NUM_1, '2': Key.NUM_2, '3': Key.NUM_3, '4': Key.NUM_4, '5': Key.NUM_5,
    '6': Key.NUM_6, '7': Key.NUM_7, '8': Key.NUM_8, '9': Key.NUM_9, '0': Key.NUM_0,
}

def parse_shortcut(shortcut_str: str) -> list[Key]:
    """Parses a human-readable string like 'Ctrl+Shift+Z' into a list of Key enums."""
    parts = [p.strip().upper() for p in shortcut_str.split('+')]
    keys = []
    for p in parts:
        if p in ALIASES:
            keys.append(ALIASES[p])
        else:
            try:
                keys.append(Key[p])
            except KeyError:
                raise ValueError(f"Unknown key or typo in shortcut: '{p}'")
    return keys

def encode_combo(shortcut: str | list[Key]) -> str:
    """
    Generates the 256-char hex string for a ButtonAssigned_X block.
    Accepts either a string ("Ctrl+S") or a list of Key Enums ([Key.CTRL, Key.S]).
    """
    keys = parse_shortcut(shortcut) if isinstance(shortcut, str) else shortcut
    events = []
    
    # 1. Key DOWN events (0x05 delay, 0x80 flag)
    for k in keys:
        events.append(f"{k.value}0580")
        
    # 2. Key UP events in REVERSE order (0x05 delay, 0x00 flag)
    for k in reversed(keys):
        events.append(f"{k.value}0500")
        
    payload = "".join(events)
    
    # Special case: Single keys mirror the keycode at the end instead of a calculated footer
    if len(keys) == 1:
        return payload[0:2] + "00" * 126 + payload[0:2]
        
    # 3. Pad with zeros to exactly 127 bytes (254 chars)
    payload_bytes = len(payload) // 2
    payload += "00" * (126 - payload_bytes)
    
    # 4. Calculate tail/footer byte (Sum of bytes 0..126 mod 256)
    # Note: We do not claim this is a checksum until proven across more samples.
    byte_array = bytes.fromhex(payload)
    footer_byte = sum(byte_array) % 256
    
    return payload + f"{footer_byte:02X}"

if __name__ == "__main__":
    # Examples from the FL Studio v1 Profile
    print("Ctrl+S (Side 5):      ", encode_combo("Ctrl+S"))
    print("Shift+F8 (Side 6):    ", encode_combo("Shift+F8"))
    print("Ctrl+Shift+Z (Side 8):", encode_combo("Ctrl+Shift+Z"))
    
    # Example using Enums directly (for internal tooling)
    print("F9 (Enum usage):      ", encode_combo([Key.F9]))
