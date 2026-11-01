import { forwardRef, useImperativeHandle, useRef } from "react";

import { formatHourLabel } from "../lib/time";

export interface DockHandle {
  reset: () => void;
}

interface HeatmapDockProps {
  startIso: string | null;
  onHour: (hour: number) => void;
  onVisible: (visible: boolean) => void;
}

export const HeatmapDock = forwardRef<DockHandle, HeatmapDockProps>(function HeatmapDock(
  { startIso, onHour, onVisible },
  ref,
) {
  const hourRef = useRef(0);
  const visibleRef = useRef(true);
  const playingRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const rangeRef = useRef<HTMLInputElement>(null);
  const playRef = useRef<HTMLButtonElement>(null);
  const heatRef = useRef<HTMLButtonElement>(null);

  function paintLabel(hour: number) {
    if (labelRef.current) {
      labelRef.current.textContent = startIso ? formatHourLabel(startIso, hour) : `+${hour}h`;
    }
    if (rangeRef.current) rangeRef.current.value = String(hour);
  }

  function stop() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    playingRef.current = false;
    if (playRef.current) playRef.current.textContent = "Play";
  }

  useImperativeHandle(ref, () => ({
    reset() {
      stop();
      hourRef.current = 0;
      paintLabel(0);
      onHour(0);
    },
  }));

  function setHour(hour: number) {
    hourRef.current = hour;
    paintLabel(hour);
    onHour(hour);
  }

  return (
    <div className="dock">
      <div className="dock-row">
        <button
          ref={playRef}
          type="button"
          onClick={() => {
            if (playingRef.current) {
              stop();
              return;
            }
            playingRef.current = true;
            if (playRef.current) playRef.current.textContent = "Pause";
            timerRef.current = window.setInterval(() => {
              const next = (hourRef.current + 1) % 49;
              setHour(next);
            }, 700);
          }}
        >
          Play
        </button>
        <label className="dock-label" htmlFor="forecast-hour">
          Corridor forecast
        </label>
        <span ref={labelRef} className="hour-readout">
          {startIso ? formatHourLabel(startIso, 0) : "+0h"}
        </span>
        <button
          ref={heatRef}
          type="button"
          aria-pressed="true"
          onClick={() => {
            visibleRef.current = !visibleRef.current;
            if (heatRef.current) {
              heatRef.current.setAttribute("aria-pressed", String(visibleRef.current));
              heatRef.current.textContent = visibleRef.current ? "Heatmap on" : "Heatmap off";
            }
            onVisible(visibleRef.current);
          }}
        >
          Heatmap on
        </button>
      </div>
      <input
        id="forecast-hour"
        ref={rangeRef}
        type="range"
        min={0}
        max={48}
        defaultValue={0}
        aria-valuemin={0}
        aria-valuemax={48}
        onInput={(event) => {
          stop();
          setHour(Number(event.currentTarget.value));
        }}
      />
    </div>
  );
});
