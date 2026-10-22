export class ImageMaskHistory {
	private snapshots: string[] = [];
	private index = -1;
	constructor(private limit = 16) {}
	get canUndo() { return this.index > 0; }
	get canRedo() { return this.index < this.snapshots.length - 1; }
	reset(snapshot: string) { this.snapshots = [snapshot]; this.index = 0; }
	commit(snapshot: string) {
		if (this.snapshots[this.index] === snapshot) return;
		this.snapshots = [...this.snapshots.slice(0, this.index + 1), snapshot].slice(-this.limit);
		this.index = this.snapshots.length - 1;
	}
	step(direction: -1 | 1) {
		const next = this.index + direction;
		if (next < 0 || next >= this.snapshots.length) return null;
		this.index = next;
		return this.snapshots[this.index];
	}
}
