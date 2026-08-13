import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Pause, Play, RotateCcw, RotateCw, Volume2, VolumeX } from "lucide-react";
import { TruncatedText } from "@/components/TruncatedText";
import { cn } from "@/lib/utils";

function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const s = Math.floor(seconds);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

const SPEEDS = [1, 1.25, 1.5, 2, 0.5] as const;

export type TimelineSegment = {
  start: number;
  end: number;
  agent: boolean;
  turnIndex?: number;
};

export type TimedTurn = {
  role: string;
  text?: string;
  start_ms?: number | null;
  end_ms?: number | null;
};

type SeekRequest = {
  sec: number;
  token: number;
};

type CallAudioPlayerProps = {
  src: string;
  agentLabel: string;
  callerLabel: string;
  segments?: TimelineSegment[];
  seekRequest?: SeekRequest | null;
  onTimeUpdate?: (time: number) => void;
  onDuration?: (duration: number) => void;
  className?: string;
};

export function CallAudioPlayer({
  src,
  agentLabel,
  callerLabel,
  segments = [],
  seekRequest = null,
  onTimeUpdate,
  onDuration,
  className,
}: CallAudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.load();
    setPlaying(false);
    setTime(0);
    setDuration(0);
  }, [src]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = speed;
  }, [speed]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = muted;
  }, [muted]);

  function seekTo(next: number) {
    const audio = audioRef.current;
    const dur = duration || audio?.duration || 0;
    if (!audio || !Number.isFinite(dur) || dur <= 0) return;
    const clamped = Math.max(0, Math.min(dur, next));
    audio.currentTime = clamped;
    setTime(clamped);
    onTimeUpdate?.(clamped);
  }

  useEffect(() => {
    if (!seekRequest) return;
    seekTo(seekRequest.sec);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- token drives seek
  }, [seekRequest?.token]);

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    } else {
      audio.pause();
      setPlaying(false);
    }
  }

  function onScrub(ev: MouseEvent<HTMLDivElement>) {
    const dur = duration || audioRef.current?.duration || 0;
    if (!dur) return;
    const rect = ev.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
    seekTo(ratio * dur);
  }

  const progressPct = duration > 0 ? (time / duration) * 100 : 0;
  const hasSegments = segments.length > 0;

  return (
    <div
      className={cn(
        "border-t border-border bg-card px-8 py-3 shadow-[0_-14px_32px_-20px_rgba(41,41,39,0.22)]",
        className,
      )}
    >
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={() => {
          const d = audioRef.current?.duration;
          if (d && Number.isFinite(d) && d > 0) {
            setDuration(d);
            onDuration?.(d);
          }
        }}
        onDurationChange={() => {
          const d = audioRef.current?.duration;
          if (d && Number.isFinite(d) && d > 0) {
            setDuration(d);
            onDuration?.(d);
          }
        }}
        onTimeUpdate={() => {
          const t = audioRef.current?.currentTime ?? 0;
          setTime(t);
          onTimeUpdate?.(t);
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      >
        <track kind="captions" />
      </audio>

      <div className="mx-auto flex w-full max-w-[1148px] flex-wrap items-center gap-x-5 gap-y-3">
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label="Back 10 seconds"
            className="inline-flex rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => seekTo(time - 10)}
          >
            <RotateCcw className="size-[17px]" />
          </button>
          <button
            type="button"
            aria-label={playing ? "Pause" : "Play"}
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-colors hover:bg-[var(--wt-green-700)] active:bg-[var(--wt-green-800)]"
            onClick={togglePlay}
          >
            {playing ? (
              <Pause className="size-4 fill-current" />
            ) : (
              <Play className="size-4 fill-current translate-x-px" />
            )}
          </button>
          <button
            type="button"
            aria-label="Forward 10 seconds"
            className="inline-flex rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => seekTo(time + 10)}
          >
            <RotateCw className="size-[17px]" />
          </button>
        </div>

        <div className="shrink-0 font-mono text-[12.5px] tracking-[-0.01em] text-foreground">
          {formatClock(time)}{" "}
          <span className="text-muted-foreground">/ {formatClock(duration)}</span>
        </div>

        <div
          role="slider"
          aria-label="Seek"
          aria-valuemin={0}
          aria-valuemax={Math.floor(duration || 0)}
          aria-valuenow={Math.floor(time)}
          tabIndex={0}
          className="relative flex h-[26px] min-w-[180px] flex-1 cursor-pointer items-center"
          onClick={onScrub}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") seekTo(time - 5);
            if (e.key === "ArrowRight") seekTo(time + 5);
          }}
        >
          {/* Track */}
          <div className="absolute inset-x-0 h-1.5 rounded-full border border-border bg-[var(--wt-section)] box-border" />

          {/* Fallback progress when no speaker capsules */}
          {!hasSegments && duration > 0 && (
            <div
              className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-primary/70"
              style={{ width: `${Math.max(progressPct, 0.5)}%` }}
            />
          )}

          {duration > 0 &&
            hasSegments &&
            segments.map((seg, i) => (
              <SpeakerSegment
                key={i}
                seg={seg}
                duration={duration}
                time={time}
              />
            ))}

          {/* Always-visible playhead */}
          <div
            className="pointer-events-none absolute top-0 z-10 h-[26px] w-0.5 rounded-sm bg-foreground shadow-[0_0_0_1px_rgba(255,255,255,0.8)]"
            style={{ left: `clamp(0px, ${progressPct}%, calc(100% - 2px))` }}
          />
        </div>

        <div className="flex min-w-0 shrink-0 items-center gap-3.5">
          <div className="hidden min-w-0 items-center gap-3 sm:flex">
            <span className="inline-flex min-w-0 max-w-[140px] items-center gap-1.5 text-[12px] text-muted-foreground">
              <span className="size-[7px] shrink-0 rounded-full bg-[var(--wt-green-600)]" />
              <TruncatedText text={agentLabel} className="text-[12px]" />
            </span>
            <span className="inline-flex min-w-0 max-w-[140px] items-center gap-1.5 text-[12px] text-muted-foreground">
              <span className="size-[7px] shrink-0 rounded-full bg-[#A7A7A5]" />
              <TruncatedText text={callerLabel} className="text-[12px]" />
            </span>
          </div>
          <div className="hidden h-5 w-px bg-border sm:block" />
          <button
            type="button"
            className="min-w-[52px] rounded-full border border-border bg-card px-3 py-1.5 font-mono text-xs font-medium text-foreground transition-colors hover:bg-muted"
            onClick={() => {
              const i = SPEEDS.indexOf(speed as (typeof SPEEDS)[number]);
              setSpeed(SPEEDS[(i + 1) % SPEEDS.length]);
            }}
          >
            {speed}x
          </button>
          <button
            type="button"
            aria-label={muted ? "Unmute" : "Mute"}
            className="inline-flex rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setMuted((m) => !m)}
          >
            {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

function SpeakerSegment({
  seg,
  duration,
  time,
}: {
  seg: TimelineSegment;
  duration: number;
  time: number;
}) {
  if (!(duration > 0) || seg.end <= seg.start) return null;

  const color = seg.agent ? "var(--wt-green-600)" : "#A7A7A5";
  const leftPct = (seg.start / duration) * 100;
  const widthPct = ((seg.end - seg.start) / duration) * 100;
  const active = time >= seg.start && time < seg.end;
  const past = time >= seg.end;

  return (
    <div
      className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full"
      style={{
        left: `${leftPct}%`,
        width: `${widthPct}%`,
        background: color,
        opacity: past || active ? 1 : 0.34,
      }}
    />
  );
}

/** True when enough turns carry real WAV offsets from recording. */
export function hasRealTimings(turns: TimedTurn[]): boolean {
  if (!turns.length) return false;
  const timed = turns.filter(
    (t) =>
      typeof t.start_ms === "number" &&
      typeof t.end_ms === "number" &&
      Number.isFinite(t.start_ms) &&
      Number.isFinite(t.end_ms) &&
      (t.end_ms as number) > (t.start_ms as number),
  );
  return timed.length >= Math.max(1, Math.ceil(turns.length * 0.5));
}

/**
 * Estimate turn spans from transcript text length vs audio duration.
 * Used when artifacts lack start_ms/end_ms (transcript JSON has no clocks).
 */
export function buildEstimatedSegments(
  turns: { role: string; text?: string }[],
  durationSec: number,
): TimelineSegment[] {
  if (!turns.length || !(durationSec > 0)) return [];

  const n = turns.length;
  const weights = turns.map((t) => Math.max((t.text || "").trim().length, 24));
  const totalWeight = weights.reduce((a, b) => a + b, 0) || 1;
  const minGap = Math.max(0.25, durationSec * 0.014);
  const gapCount = Math.max(0, n - 1);
  let gapTotal = gapCount * minGap;
  const trailing = Math.max(0.3, durationSec * 0.05);
  const leading = Math.min(0.15, durationSec * 0.01);
  let speechBudget = durationSec - gapTotal - trailing - leading;
  if (speechBudget < durationSec * 0.5) {
    const floorGap = Math.max(0.15, durationSec * 0.006);
    gapTotal = gapCount * floorGap;
    speechBudget = Math.max(
      durationSec * 0.5,
      durationSec - gapTotal - trailing - leading,
    );
  }
  const gap = gapCount > 0 ? gapTotal / gapCount : 0;

  let cursor = leading;
  const segs: TimelineSegment[] = [];
  for (let i = 0; i < n; i++) {
    const speech = (weights[i] / totalWeight) * speechBudget;
    const start = cursor;
    const end = Math.min(durationSec - trailing * 0.25, start + Math.max(speech, 0.2));
    const isCaller = turns[i].role === "user" || turns[i].role === "caller";
    segs.push({ start, end, agent: !isCaller, turnIndex: i });
    cursor = end + (i < n - 1 ? gap : 0);
  }
  return segs.filter((s) => s.end > s.start);
}

/**
 * Prefer real offsets on turns (provider word clocks or CallRecorder);
 * otherwise estimate from transcript text length.
 */
export function buildSpeechSegments(
  turns: TimedTurn[],
  durationSec: number,
): TimelineSegment[] {
  if (!turns.length || !(durationSec > 0)) return [];

  if (hasRealTimings(turns)) {
    const segs: TimelineSegment[] = [];
    turns.forEach((t, i) => {
      if (
        typeof t.start_ms !== "number" ||
        typeof t.end_ms !== "number" ||
        !Number.isFinite(t.start_ms) ||
        !Number.isFinite(t.end_ms)
      ) {
        return;
      }
      const start = Math.max(0, Math.min(durationSec, t.start_ms / 1000));
      const end = Math.max(start, Math.min(durationSec, t.end_ms / 1000));
      if (end <= start) return;
      const isCaller = t.role === "user" || t.role === "caller";
      segs.push({ start, end, agent: !isCaller, turnIndex: i });
    });
    if (segs.length) return segs;
  }

  return buildEstimatedSegments(turns, durationSec);
}

export function activeSegmentIndex(
  segments: TimelineSegment[],
  time: number,
): number | null {
  if (!segments.length) return null;
  for (let i = 0; i < segments.length; i++) {
    const s = segments[i];
    if (time >= s.start && time < s.end) {
      return s.turnIndex ?? i;
    }
  }
  return null;
}

export { formatClock };
