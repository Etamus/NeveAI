class HaruCapture extends AudioWorkletProcessor {
	constructor() {
		super();
		this.frame = new ArrayBuffer(Math.round(sampleRate * 0.04) * 2);
		this.samples = new DataView(this.frame);
		this.offset = 0;
		this.muted = false;
		this.port.onmessage = ({ data }) => { this.muted = data === true; };
	}

	process(inputs, outputs) {
		outputs[0]?.[0]?.fill(0);
		for (const sample of inputs[0]?.[0] ?? []) {
			const value = this.muted ? 0 : Math.max(-1, Math.min(1, sample));
			this.samples.setInt16(this.offset, value * (value < 0 ? 32768 : 32767), true);
			this.offset += 2;
			if (this.offset === this.frame.byteLength) {
				const size = this.frame.byteLength;
				this.port.postMessage(this.frame, [this.frame]);
				this.frame = new ArrayBuffer(size);
				this.samples = new DataView(this.frame);
				this.offset = 0;
			}
		}
		return true;
	}
}

registerProcessor('haru-capture', HaruCapture);
