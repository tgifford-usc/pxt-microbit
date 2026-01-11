namespace pxsim {
    const SERIAL_BUFFER_LENGTH = 16;

    function normalizeDelimiter(d: string): string {
       if (!d) return "";

        // Common cases:
        // "\n" actual newline -> keep
        // "\\n" two characters -> convert to newline
        // "10" etc -> leave alone (we only support string delimiters)
        if (d === "\\n") return "\n";
        if (d === "\\r") return "\r";
        if (d === "\\r\\n") return "\r\n";

        return d;
    }

    export class SerialState {
        // Keep a single RX string buffer rather than string[] chunks.
        private rxBuffer = "";
        // Track delimiters registered via onDataReceived
        private delimiters = new Set<string>();

        constructor(private readonly runtime: Runtime, private readonly board: BaseBoard) {
            this.board.addMessageListener(this.handleMessage.bind(this))
        }

        private handleMessage(msg: SimulatorMessage) {
            if (msg.type === "serial") {
                const data = (msg as SimulatorSerialMessage).data || "";
                this.receiveData(data);
            }
        }

        /** Called when serial data arrives *into* the simulator (web -> sim) */
        public receiveData(data: string) {
            if (!data) return;

            this.rxBuffer += data;

            // Fire delimiter event if any registered delimiter appears
            for (const d of this.delimiters) {
                const delim = normalizeDelimiter(d);
                if (!delim) continue;

                if (this.rxBuffer.indexOf(delim) !== -1) {
                    // IMPORTANT: use the current runtime board bus (same one as serial.onDataReceived)
                    const b = pxsim.board();
                    b?.bus?.queue(
                        DAL.MICROBIT_ID_SERIAL,
                        DAL.MICROBIT_SERIAL_EVT_DELIM_MATCH
                    );
                    // Don't break; allow multiple delimiters
                }
            }
        }

        /** Read buffered received data (sim version) */
        readSerial() {
            // Return everything we have, then clear (matches readBuffer-ish semantics)
            const v = this.rxBuffer;
            this.rxBuffer = "";
            return v;
        }

        readUntil(delim: string): string {
            const d = normalizeDelimiter(delim);
            if (!d) {
                const v = this.rxBuffer;
                this.rxBuffer = "";
                return v;
            }

            const idx = this.rxBuffer.indexOf(d);
            if (idx === -1) return "";

            const out = this.rxBuffer.slice(0, idx);
            this.rxBuffer = this.rxBuffer.slice(idx + d.length);
            return out;
        }


        /** Allow serial.onDataReceived to register delimiters */
        registerDelimiter(delims: string) {
            // In the runtime, delimiters are typically single chars; accept any string.
            // If callers pass something like "\n", store it as-is.
            if (!delims) return;
            this.delimiters.add(delims);
        }

        serialOutBuffer: string = "";
        writeSerial(s: string) {
            this.serialOutBuffer += s;
            if (/\n/.test(this.serialOutBuffer) || this.serialOutBuffer.length > SERIAL_BUFFER_LENGTH) {
                Runtime.postMessage(<SimulatorSerialMessage>{
                    type: 'serial',
                    data: this.serialOutBuffer,
                    id: runtime.id,
                    sim: true
                })
                this.serialOutBuffer = '';
            }
        }

        writeCsv(s: string, type: "headers" | "row" | "clear") {
            Runtime.postMessage(<SimulatorSerialMessage>{
                type: 'serial',
                data: s,
                id: runtime.id,
                csvType: type,
                sim: true
            })
        }
    }
}


namespace pxsim.serial {
    export function writeString(s: string) {
        board().writeSerial(s);
    }

    export function writeBuffer(buf: RefBuffer) {
        // TODO
    }

    // export function readUntil(del: string): string {
    //     const s = readString();
    //     if (!del) return s;

    //     const idx = s.indexOf(del);
    //     if (idx === -1) {
    //         // put it back if delimiter not found
    //         board().serialState.receiveData(s);
    //         return "";
    //     }
    //     const out = s.slice(0, idx);
    //     const rest = s.slice(idx + del.length);
    //     if (rest) board().serialState.receiveData(rest);
    //     return out;
    // }
    export function readUntil(del: string): string {
        return board().serialState.readUntil(del);
    }

    export function readString(): string {
        return board().serialState.readSerial();
    }

    export function onDataReceived(delimiters: string, handler: RefAction) {
        const b = board();
        b.serialState.registerDelimiter(delimiters);
        b.bus.listen(DAL.MICROBIT_ID_SERIAL, DAL.MICROBIT_SERIAL_EVT_DELIM_MATCH, handler);
    }

    export function redirect(tx: number, rx: number, rate: number) {
        // TODO?
    }

    export function redirectToUSB() {
        // TODO
    }

    export function setRxBufferSize(size: number) {
        // TODO
    }

    export function setTxBufferSize(size: number) {
        // TODO
    }

    export function readBuffer(length: number) {
        length |= 0;
        if (length <= 0)
            length = 64;
        return pins.createBuffer(length);
    }

    export function setBaudRate(rate: number) {
        // TODO
    }

    export function writeDmesg() {
        // TODO
    }

    export function inject(data: string) {
        board().serialState.receiveData(data);
    }
}