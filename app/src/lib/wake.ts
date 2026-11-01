// Wake-word listening: while on, every utterance the mic hears is cut out by a simple voice-activity detector and
// sent to the engine as a WAV clip. The engine recognises it on this Mac and only acts when it starts with
// "Hey Agent" (engine/models/wake.py). Lives at the App level so it keeps listening while the panel is collapsed.
import { useCallback, useEffect, useRef, useState } from "react";

// "command": a bare start word was heard and the next utterance is the task. (Ordinary sounds don't change the state,
// so the mic button and the input box stay steady.)
export type WakeState = "off" | "listening" | "command";

const RATE = 16000;
const PRE_ROLL_S = 0.4; // audio kept from just before speech started, so the first word isn't clipped
const END_SILENCE_S = 1.2; // this much quiet ends an utterance (shorter splits sentences at a pause)
const MAX_UTTERANCE_S = 12;
const MIN_SPEECH_S = 0.35;
const ONSET_FRAMES = 2; // loud frames in a row (about 0.25s) before it counts as speech: clicks and taps don't
const OVER_SPEECH_S = 2.0; // while Deskwright talks the room never goes quiet: send what it hears in short pieces
const COMMAND_WINDOW_MS = 7000; // after a bare "Hey Agent", how long the next utterance counts as the task

function wav(samples: Float32Array, rate: number): Uint8Array {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, "data");
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, samples[i])) * 0x7fff, true);
  return new Uint8Array(buf);
}

function base64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function load(): boolean {
  try {
    return localStorage.getItem("wake") === "1";
  } catch {
    return false;
  }
}

function save(on: boolean) {
  try {
    localStorage.setItem("wake", on ? "1" : "0");
  } catch {
    /* private mode: just not remembered */
  }
}

/** `speaking`: Deskwright is talking. Listening goes on meanwhile (so "stop" or the start word can cut it off); the
 * engine removes its own words from what the mic heard. */
export function useWakeWord(send: (msg: Record<string, unknown>) => void, speaking: boolean, answering = false) {
  const [on, setOn] = useState(load);
  const [state, setState] = useState<WakeState>("off");
  const commandUntil = useRef(0);
  const speakingRef = useRef(speaking);
  speakingRef.current = speaking;
  // A question from the task is waiting: the next thing said is the answer (no "agent input" needed).
  const answeringRef = useRef(answering);
  answeringRef.current = answering;

  useEffect(() => {
    if (!on) {
      setState("off");
      return;
    }
    let stopped = false;
    let ctx: AudioContext | null = null;
    let stream: MediaStream | null = null;
    (async () => {
      try {
        await window.agent?.askMicrophone();
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
        if (stopped) return stream.getTracks().forEach((t) => t.stop());
        ctx = new AudioContext({ sampleRate: RATE });
        const src = ctx.createMediaStreamSource(stream);
        const node = ctx.createScriptProcessor(2048, 1, 1);
        const pre: Float32Array[] = [];
        let take: Float32Array[] | null = null;
        let speech = 0;
        let quiet = 0;
        let onset = 0;
        let overSpeech = false; // Deskwright talked during this clip
        const levels: number[] = []; // recent loudness, to tell the room's background from speech
        const frameS = 2048 / RATE;
        setState("listening");
        node.onaudioprocess = (e) => {
          const x = new Float32Array(e.inputBuffer.getChannelData(0));
          let sum = 0;
          for (let i = 0; i < x.length; i++) sum += x[i] * x[i];
          const rms = Math.sqrt(sum / x.length);
          // Background = the quieter end of the last few seconds, so it follows the room up as well as down (a fan
          // or music starting would otherwise read as one endless sentence).
          levels.push(rms);
          if (levels.length * frameS > 4) levels.shift();
          const floor = [...levels].sort((a, b) => a - b)[Math.floor(levels.length * 0.2)] ?? 0.01;
          const loud = rms > Math.max(0.02, floor * 2.5);
          if (!take) {
            pre.push(x);
            while (pre.length * frameS > PRE_ROLL_S) pre.shift();
            onset = loud ? onset + 1 : 0;
            // While Deskwright talks its own voice sets the background level, so a person talking over it may never
            // read as "loud": record continuously then, in short pieces (the engine finds the user's words).
            if (onset >= ONSET_FRAMES || speakingRef.current) {
              take = [...pre]; // the pre-roll already holds the loud frames
              speech = onset * frameS;
              quiet = 0;
              onset = 0;
              overSpeech = speakingRef.current;
            }
            return;
          }
          take.push(x);
          if (speakingRef.current) overSpeech = true;
          if (loud) {
            speech += frameS;
            quiet = 0;
          } else quiet += frameS;
          const length = take.length * frameS;
          if (quiet >= END_SILENCE_S || length >= (overSpeech ? OVER_SPEECH_S : MAX_UTTERANCE_S)) {
            const clip = take;
            const duringSpeech = overSpeech;
            take = null;
            pre.length = 0;
            const isCommand = Date.now() < commandUntil.current;
            if (speech < MIN_SPEECH_S && !duringSpeech) return;
            const all = new Float32Array(clip.reduce((n, c) => n + c.length, 0));
            let o = 0;
            for (const c of clip) {
              all.set(c, o);
              o += c.length;
            }
            if (isCommand) commandUntil.current = 0;
            send({ type: "wake_audio", data: base64(wav(all, RATE)), mime: "audio/wav", command: isCommand,
              during_speech: duringSpeech, answer: answeringRef.current });
          }
        };
        src.connect(node);
        node.connect(ctx.destination);
      } catch (err) {
        console.error("wake word microphone", err);
        setOn(false);
        save(false);
      }
    })();
    return () => {
      stopped = true;
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => {});
    };
  }, [on, send]);

  /** The engine heard a bare "Hey Agent": treat the next utterance as the task. */
  const heard = useCallback(() => {
    commandUntil.current = Date.now() + COMMAND_WINDOW_MS;
    setState("command");
    setTimeout(() => setState((s) => (s === "command" && Date.now() >= commandUntil.current ? "listening" : s)),
      COMMAND_WINDOW_MS + 50);
  }, []);

  const toggle = useCallback(() => {
    setOn((v) => {
      save(!v);
      return !v;
    });
  }, []);

  return { on, state, toggle, heard, off: () => { setOn(false); save(false); } };
}
