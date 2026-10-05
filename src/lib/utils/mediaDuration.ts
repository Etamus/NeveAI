export function mediaDuration(media: Pick<HTMLMediaElement, 'duration' | 'buffered'>): number {
	if (Number.isFinite(media.duration) && media.duration > 0) return media.duration;
	const buffered = media.buffered;
	const end = buffered.length ? buffered.end(buffered.length - 1) : 0;
	return Number.isFinite(end) && end > 0 ? end : 0;
}
