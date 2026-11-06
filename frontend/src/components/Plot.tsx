import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";

const DARK_LAYOUT: any = {
  paper_bgcolor: "#121318",
  plot_bgcolor: "#0a0b0e",
  font: { color: "#9aa0ab", size: 11 },
  margin: { l: 50, r: 20, t: 24, b: 40 },
  xaxis: { gridcolor: "#23262f", zerolinecolor: "#2a2d37" },
  yaxis: { gridcolor: "#23262f", zerolinecolor: "#2a2d37" },
};

export function Plot({
  data,
  layout,
  height = 300,
  onRelayout,
}: {
  data: any[];
  layout?: any;
  height?: number;
  onRelayout?: (e: any) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const merged = {
      ...DARK_LAYOUT,
      ...layout,
      xaxis: { ...DARK_LAYOUT.xaxis, ...(layout?.xaxis || {}) },
      yaxis: { ...DARK_LAYOUT.yaxis, ...(layout?.yaxis || {}) },
      height,
      autosize: true,
    };
    Plotly.react(ref.current, data, merged, {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    });
    const el = ref.current as any;
    if (onRelayout) el.on?.("plotly_relayout", onRelayout);
    return () => {
      if (el) Plotly.purge(el);
    };
  }, [data, layout, height, onRelayout]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
