---
title: 附录 B (资料性) 事件组传输配置方式
short_title: 附录 B (资料性) 事件组传输配置方式
description: GB/T 46803.1-2025 · 附录 B (资料性) 事件组传输配置方式
numbering:
  headings: false
  figure: false
  table: false
  equation: false
  subequation: false
---

# 附录 B (资料性) 事件组传输配置方式

:::{div}
:class: standard-paragraph

<p>通过合理的参数设置,事件组集合内多个事件组的时间资源可配置为串行方式、交织方式和混合方式。</p>

:::

:::{div}
:class: standard-paragraph

<p>串行方式的传输如图B.1所示。</p>

:::

```{image} ../../../assets/structured/GBT-46803.1-2025/diagrams/figure-b-1-structured.svg
:alt: 图 B.1　串行方式的传输。连续两个事件组，保留两条链路的起始调度点、事件间隔、事件组周期间隔及各传输方向。
:class: standard-vector-figure
```

(gbt-46803-1-2025-figure-b-1)=
:::{div}
:class: standard-caption

<p>图 B.1　串行方式的传输</p>

:::

:::{div}
:class: standard-paragraph

<p>交织方式的传输如图B.2所示。</p>

:::

```{image} ../../../assets/structured/GBT-46803.1-2025/diagrams/figure-b-2-structured.svg
:alt: 图 B.2　交织方式传输。连续两个事件组，保留两条链路的起始调度点、事件间隔、事件组周期间隔及各传输方向。
:class: standard-vector-figure
```

(gbt-46803-1-2025-figure-b-2)=
:::{div}
:class: standard-caption

<p>图 B.2　交织方式传输</p>

:::

:::{div}
:class: standard-paragraph

<p>混合方式的传输如图B.3所示。</p>

:::

```{image} ../../../assets/structured/GBT-46803.1-2025/diagrams/figure-b-3-structured.svg
:alt: 图 B.3　混合方式的传输。连续两个事件组，保留两条链路的起始调度点、事件间隔、事件组周期间隔及各传输方向。
:class: standard-vector-figure
```

(gbt-46803-1-2025-figure-b-3)=
:::{div}
:class: standard-caption

<p>图 B.3　混合方式的传输</p>

:::

:::{div}
:class: standard-paragraph

<p>混合方式包括传输阶段和重传阶段:传输阶段用于传输新数据,占用时长是传输新包个数个事件间隔的总和;重传阶段用于重传数据,占用时长是每条链路重传[事件总数-新包个数]个事件间隔的总和。</p>

:::
