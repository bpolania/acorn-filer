# Acorn Archimedes Serial Communication Tools

This repository contains BBC BASIC programs and utilities for serial communication between modern computers (Raspberry Pi/PC) and Acorn Archimedes computers using RS-423.

## BBC BASIC Programs

### MINRX - Minimal Receiver
Diagnostic program that displays received bytes in hexadecimal format.
- Shows each byte as `~XX` where XX is the hex value
- Useful for verifying reception and debugging framing issues

### SERIALRW - Send/Receive Program  
Full bidirectional serial communication program.
- Sends user input to serial port
- Waits for response with 1-minute timeout
- Displays received characters

### BAUDSCAN - Baud Rate Scanner
Automatically detects correct baud rate and parity settings.
- Tests common baud rates (300-115200)
- Shows byte counts and most common received byte
- Helps identify correct communication parameters

### FILERCV - File Receiver
Receives data over serial and saves to a file.
- Saves received data to "RECEIVE" file
- Sets BASIC filetype (&FFB) automatically
- 1-minute timeout after last byte received

## File Transfer to Archimedes

### Via DOS Diskette (720k)

1. Format diskette on Archimedes using DOS 720k format
2. Copy files to diskette on PC:
```powershell
copy MINRX A:\MINRX
copy SERIALRW A:\SERIALRW
copy BAUDSCAN A:\BAUDSCAN
copy FILERCV A:\FILERCV
```
3. On Archimedes, set BASIC filetype:
```
*SETTYPE MINRX &FFB
*SETTYPE SERIALRW &FFB
*SETTYPE BAUDSCAN &FFB
*SETTYPE FILERCV &FFB
```

## Testing Strategy

### Prerequisites
- Null-modem cable between Pi/PC and Archimedes
- USB-to-serial adapter on Pi/PC
- Python 3 with pyserial module
- `serial_tool.py` script (included in repo)

### Test 1: Basic Reception
Verify that Archimedes can receive characters.

**On Pi/PC:**
```bash
python3 serial_tool.py --port /dev/ttyUSB0 --mode send --baud 9600 --rtscts 1 --dsrdtr 1 --crlf cr
```

**On Archimedes:**
```
*SETTYPE MINRX &FFB
RUN "MINRX"
```

**Test:** Type single characters on Pi. Should see hex values on Archimedes:
- 'A' → `~41`
- 'B' → `~42`  
- '1' → `~31`
- Enter → `~0D`

### Test 2: Auto-Pattern Detection
Test with automatic patterns to verify consistent reception.

**On Pi/PC:** 
```bash
python3 serial_tool.py --port /dev/ttyUSB0 --mode send --baud 9600 --rtscts 1 --dsrdtr 1
# Automatically sends 256-byte pattern then U's at 10Hz
```

**On Archimedes:** Keep MINRX running
- Should see `~00 ~01 ~02...~FF` (256-byte pattern)
- Then repeated `~55` (U pattern)

### Test 3: Interactive Echo Test
Test bidirectional communication.

**On Pi/PC:**
```bash
python3 serial_tool.py --port /dev/ttyUSB0 --mode send --baud 9600 --rtscts 1 --dsrdtr 1 --crlf cr
```

**On Archimedes:**
```
*SETTYPE SERIALRW &FFB
RUN "SERIALRW"
```

**Test sequence:**
1. Type "HELLO" on Archimedes → Pi shows RX byte counts
2. Type "WORLD" on Pi → Archimedes displays "WORLD"
3. Test special characters: "123!@#" both ways

### Test 4: Baud Rate Confirmation
Verify correct baud rate settings.

**On Pi/PC:** Run continuous U pattern:
```bash
while true; do echo -n "U"; done | python3 serial_tool.py --port /dev/ttyUSB0 --mode send --baud 9600 --rtscts 1 --dsrdtr 1
```

**On Archimedes:**
```
*SETTYPE BAUDSCAN &FFB
RUN "BAUDSCAN"
```

Expected: Highest byte count at `mode=0 idx=6` with `top=~55`

## Troubleshooting

### No Reception
Try without hardware handshaking:
```bash
python3 serial_tool.py --port /dev/ttyUSB0 --mode send --baud 9600 --rtscts 0 --dsrdtr 0
```

On Archimedes, disable input handshaking:
```
*FX 8,0
```

### Garbage Characters
Scan for correct baud rate:
```bash
python3 serial_tool.py --port /dev/ttyUSB0 --mode scan
```

### Monitor Raw Data from Archimedes
```bash
python3 serial_tool.py --port /dev/ttyUSB0 --mode dump --hex
```

## Technical Details

### Serial Configuration
- Default: 9600 baud, 8N1
- Hardware handshaking: RTS/CTS enabled
- Status bit for data ready: `&04`
- Timeout: 6000 centiseconds (1 minute)

### RISC OS Serial Operations
- `SYS "OS_SerialOp",0,idx,mode` - Set baud rate
- `SYS "OS_SerialOp",1,mode` - Set data format
- `SYS "OS_SerialOp",2 TO b%` - Read byte
- `SYS "OS_SerialOp",3,ch%` - Send byte
- `SYS "OS_SerialOp",4 TO s%` - Get status
- `SYS "OS_SerialOp",5,7` - Set stream 7 for input
- `SYS "OS_SerialOp",6,7` - Set stream 7 for output

### Python Script Features
- **dump mode**: Display received bytes
- **send mode**: Interactive sending with automatic test patterns
- **scan mode**: Auto-detect baud rate
- **loopback mode**: Test cable connections
- Supports hardware/software flow control
- Logging capability with `--log` flag

## Requirements

### Archimedes
- RISC OS 2 or later
- Working serial port (RS-423)
- DOS-compatible diskette drive (720k)

### Modern Computer (Pi/PC)
- Python 3.x
- pyserial module (`pip install pyserial`)
- USB-to-serial adapter
- Null-modem cable

## License
Public Domain - Use freely for testing Acorn Archimedes serial communications.