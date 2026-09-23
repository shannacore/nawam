/* Monitor-bound license layout, independent of Win32 for regression tests. */
#ifndef NAWAM_LAYOUT_H
#define NAWAM_LAYOUT_H

typedef struct {
	int x, y, width, height;
} NawamLayoutRect;

/* Controls in reading order: notice, label, credits, label, GPL, Close.
 * All inputs are measured pixels, including the actual non-client frame.
 * Keep fonts, labels, gaps and Close intact; only scrollable panes shrink.
 */
static int NawamFitLicenseLayout(const NawamLayoutRect* work, NawamLayoutRect* window,
	int frame_width, int frame_height, NawamLayoutRect controls[6])
{
	int i, width, height, dx, available, total, remaining, weight, y;
	int gaps[6];

	if (work->width <= frame_width || work->height <= frame_height)
		return 0;
	width = window->width < work->width ? window->width : work->width;
	height = window->height < work->height ? window->height : work->height;
	dx = width - window->width;
	total = controls[0].height + controls[2].height + controls[4].height;
	available = total + height - window->height;
	if (total <= 0 || available < 3 || controls[5].width > width - frame_width)
		return 0;
	for (i = 0; i < 5; i++) {
		if (controls[i].width + dx <= 0)
			return 0;
	}
	gaps[0] = controls[0].y;
	for (i = 1; i < 6; i++)
		gaps[i] = controls[i].y - controls[i - 1].y - controls[i - 1].height;

	remaining = available;
	weight = total;
	y = 0;
	for (i = 0; i < 6; i++) {
		y += gaps[i];
		controls[i].y = y;
		if (i == 0 || i == 2 || i == 4) {
			int old_height = controls[i].height;
			controls[i].height = remaining * old_height / weight;
			remaining -= controls[i].height;
			weight -= old_height;
		}
		if (i < 5)
			controls[i].width += dx;
		else if (controls[i].x > (window->width - frame_width) / 2)
			controls[i].x += dx;
		y += controls[i].height;
	}
	window->width = width;
	window->height = height;
	if (window->x > work->x + work->width - width)
		window->x = work->x + work->width - width;
	if (window->x < work->x)
		window->x = work->x;
	if (window->y > work->y + work->height - height)
		window->y = work->y + work->height - height;
	if (window->y < work->y)
		window->y = work->y;
	return 1;
}

#endif
