#!/usr/bin/env python3
"""Generate the UWB time templates in GB/T 48336.101 and GB/T 48336.201."""

from math import sqrt
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BETA = 10
HALF_DURATION = 1.5  # Both references specify a duration of 3 T_p.


def i0(x):
    """Zeroth-order modified Bessel function from its convergent series."""
    term = total = 1.0
    order = 0
    while term > total * 1e-16:
        order += 1
        term *= (x / (2 * order)) ** 2
        total += term
    return total


PEAK = i0(BETA)


def kaiser_amplitude(t):
    """Evaluate r(t)/r(0) with time expressed in units of T_p."""
    if abs(t) > HALF_DURATION:
        return 0.0
    return i0(BETA * sqrt(1 - (t / HALF_DURATION) ** 2)) / PEAK


def x_at(t):
    return 76 + (t + 4) * 75


def y_at(amplitude):
    return 41 + (1 - amplitude) * 276


def point(t, amplitude):
    return f'{x_at(t):.2f} {y_at(amplitude):.2f}'


def tick(value):
    return f'{value:g}'.replace('-', '−')


def template_figure(part, figure, equation, limit, markers):
    title = f'图 {figure}　超宽带脉冲时域波形模板'
    mask = [
        (-4, limit), (-1.87, limit), (-1.87, .04), (-1.37, .04),
        (-1.37, .3), (-.88, .3), (-.88, 1), (.88, 1), (.88, .3),
        (1.37, .3), (1.37, .04), (1.87, .04), (1.87, limit), (4, limit),
    ]
    times = [3 * i / 240 - HALF_DURATION for i in range(241)]
    pulse = [
        (-4, 0), (-HALF_DURATION, 0),
        *((t, kaiser_amplitude(t)) for t in times),
        (HALF_DURATION, 0), (4, 0),
    ]
    labels = [
        ('A', (.88, .3), (1.15, .43)),
        ('B', (1.37, .3), (1.66, .39)),
        ('C', (1.37, .04), (1.72, .17)),
        ('D', (1.87, .04), (2.25, .22)),
        ('E', (1.87, limit), (2.47, .12)),
        ('F', (.30, -limit), (.9, -.10)),
    ]
    ticks = (-.2, 0, .2, .4, .6, .8, 1)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 468" role="img" aria-labelledby="title description">',
        f'<title id="title">{title}</title>',
        f'<desc id="description">虚线为 GB/T 48336.{part}—2026 式（{equation}）的凯撒参考波形，峰值归一化。实线是时域模板，A 至 F 的坐标及方程见图下表格。</desc>',
    ]
    if markers:
        lines.append('<defs><marker id="leader" viewBox="0 0 8 8" refX="7.6" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path fill="#27313a" d="M0 0L8 4L0 8Z"/></marker></defs>')
    lines.extend([
        '<rect width="700" height="468" fill="white"/>',
        '<g fill="none" stroke="#d1d5d9" stroke-width="1">',
        *(f'<path d="M{point(t, 1)}V{y_at(-.2):.2f}"/>' for t in range(-3, 4)),
        *(f'<path d="M{point(-4, a)}H{x_at(4):.2f}"/>' for a in ticks[1:-1]),
        '</g>',
        f'<rect x="{x_at(-4):.2f}" y="{y_at(1):.2f}" width="600" height="{y_at(-.2)-y_at(1):.2f}" fill="none" stroke="#5c656d" stroke-width="1.1"/>',
        '<g fill="none" stroke="#5c656d" stroke-width="1.1">',
        *(f'<path d="M{point(t, -.2)}v5M{point(t, 1)}v4"/>' for t in range(-4, 5)),
        *(f'<path d="M{point(-4, a)}h-5M{point(4, a)}h-4"/>' for a in ticks),
        '</g>',
        '<g fill="none" stroke="#657481" stroke-width="2.2">',
        f'<path d="M{" L".join(point(*node) for node in mask)} M{point(-4, -limit)}H{x_at(4):.2f}"/>',
        '<path d="M112 449H147"/>',
        '</g>',
        '<g fill="none" stroke="#20252b" stroke-width="1.9" stroke-dasharray="7,4">',
        f'<path d="M{" L".join(point(*node) for node in pulse)}"/>',
        '<path d="M291 449H326"/>',
        '</g>',
    ])
    marker = ' marker-end="url(#leader)"' if markers else ''
    for _, (t, a), (lx, ly) in labels:
        lines.append(f'<path d="M{point(lx-.035, ly-.019)}L{point(t, a)}" fill="none" stroke="#27313a" stroke-width="1"{marker}/>')
        if not markers:
            lines.append(f'<circle cx="{x_at(t):.2f}" cy="{y_at(a):.2f}" r="2.6" fill="#27313a"/>')
    lines.extend([
        '<g fill="#20252b" font-family="system-ui, sans-serif" font-size="16">',
        '<text x="376" y="26" text-anchor="middle" font-size="19">时域模板</text>',
        *(f'<text x="{x_at(t):.2f}" y="{y_at(a):.2f}">{symbol}</text>' for symbol, _, (t, a) in labels),
        *(f'<text x="{x_at(t):.2f}" y="392" text-anchor="middle">{tick(t)}</text>' for t in range(-4, 5)),
        *(f'<text x="65" y="{y_at(a)+5:.2f}" text-anchor="end">{tick(a)}</text>' for a in ticks),
        '<text x="376" y="422" text-anchor="middle">时间（T<tspan baseline-shift="sub" font-size="11">p</tspan>）</text>',
        '<text x="22" y="207" text-anchor="middle" transform="rotate(-90 22 207)">相对幅度</text>',
        '<text x="154" y="454">时域模板</text>',
        '<text x="333" y="454">凯撒参考波形（峰值归一化）</text>',
        '</g>',
        '</svg>',
    ])
    return '\n'.join(lines) + '\n'


def main():
    for part, figure, equation, limit, markers, asset in (
        (101, 6, 1, .015, True, 151),
        (201, 5, 21, .025, False, 163),
    ):
        path = ROOT / f'assets/structured/GBT-48336.{part}-2026/diagrams/uwb-time-template-{asset}.svg'
        path.write_text(template_figure(part, figure, equation, limit, markers), encoding='utf-8')


if __name__ == '__main__':
    main()
