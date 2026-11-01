// Vector version of the app icon (generated with Muse Image): a pointer and a text caret on a black tile.
export function Logo({ size = 22, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8.5" fill="#141414" />
      <path d="M9.4 7.6 L22.2 13.9 L17.4 15.7 L20.6 20.4 L18.4 22.1 L15.1 17.5 L11.6 21.1 Z" fill="#fff" />
      <path d="M23.3 19.6 v6.2 M22.1 19.6 h2.4 M22.1 25.8 h2.4" stroke="#fff" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}
