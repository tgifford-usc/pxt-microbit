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

    
        // private raiseSerialDelimMatch() {
        //     const bus: any = (this.board as any)?.bus;
        //     if (!bus?.queue) return;

        //     const id = DAL.MICROBIT_ID_SERIAL;
        //     const evt = DAL.MICROBIT_SERIAL_EVT_DELIM_MATCH;

        //     // Queue the event with a numeric value
        //     bus.queue(id, evt, 0);

        //     // Poke the simulator to process pending work
        //     // (microtask yields back into the sim's scheduler)
        //     Promise.resolve().then(() => {
        //         // Some builds have runtime.updateDisplay / queueDisplayUpdate
        //         const rt: any = (this.runtime as any);
        //         if (!rt.running) { console.log("WARNING: Runtime is not Running"); }


        //         if (typeof rt.queueDisplayUpdate === "function") rt.queueDisplayUpdate();
        //         else if (typeof rt.updateDisplay === "function") rt.updateDisplay();
        //         else if (typeof rt.runPending === "function") rt.runPending();
        //         // else: nothing available; microtask yield alone often suffices
        //     });
        // }

        /** Called when serial data arrives *into* the simulator (web -> sim) */
        public receiveData(data: string) {
            
            console.log("receiveData", JSON.stringify(data), data.split("").map(c=>c.charCodeAt(0)));
            
            if (!data) return;

            this.rxBuffer += data;
            console.log("rxBuffer now", JSON.stringify(this.rxBuffer));
            
            // Fire delimiter event if any registered delimiter appears
            for (const d of this.delimiters) {
                const delim = normalizeDelimiter(d);
                if (!delim) continue;

                console.log("QUEUEING DELIM MATCH", {
                    sid: (this as any).__sid,
                    delim,
                    rx: JSON.stringify(this.rxBuffer),
                    id: DAL.MICROBIT_ID_SERIAL,
                    evt: DAL.MICROBIT_SERIAL_EVT_DELIM_MATCH
                });
                
                if (this.rxBuffer.indexOf(delim) !== -1) {
                    pxsim.control.raiseEvent(DAL.MICROBIT_ID_SERIAL, DAL.MICROBIT_SERIAL_EVT_DELIM_MATCH, 0);
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
            if (!delims) return;

            const d = normalizeDelimiter(delims);
            this.delimiters.add(d);

            // Catch-up: if data already arrived and contains the delimiter,
            // trigger the same event hardware would raise.
            if (d && this.rxBuffer.indexOf(d) !== -1) {
                pxsim.control.raiseEvent(DAL.MICROBIT_ID_SERIAL, DAL.MICROBIT_SERIAL_EVT_DELIM_MATCH, 0);
            }
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
        const b: any = pxsim.board();
        if (!b || !b.serialState) return;
        b.serialState.receiveData(data);
    }
}