/**
 * Dark, warm plated-dish backdrop drawn in SVG so the landing page works with
 * no image files. To use a real photograph, put it at public/hero.jpg: it is
 * layered over this artwork automatically.
 */
export function HeroArt() {
  return (
    <div className="absolute inset-0 overflow-hidden bg-night" aria-hidden="true">
      <svg className="absolute inset-0 size-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
        <defs>
          <radialGradient id="glow" cx="72%" cy="48%" r="60%">
            <stop offset="0" stopColor="#7a4120" stopOpacity="0.85" />
            <stop offset="0.55" stopColor="#2b160c" stopOpacity="0.6" />
            <stop offset="1" stopColor="#140d0b" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="plate" cx="45%" cy="40%" r="70%">
            <stop offset="0" stopColor="#4a3022" />
            <stop offset="0.7" stopColor="#24150e" />
            <stop offset="1" stopColor="#100a07" />
          </radialGradient>
          <radialGradient id="sauce" cx="50%" cy="45%" r="60%">
            <stop offset="0" stopColor="#6a3515" />
            <stop offset="1" stopColor="#2a1409" />
          </radialGradient>
          <linearGradient id="salmon" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#f6a15d" />
            <stop offset="0.55" stopColor="#e2713a" />
            <stop offset="1" stopColor="#b3481b" />
          </linearGradient>
          <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#6b4a36" />
            <stop offset="1" stopColor="#1a100b" />
          </linearGradient>
          <filter id="soft"><feGaussianBlur stdDeviation="1.4" /></filter>
          <filter id="bokeh"><feGaussianBlur stdDeviation="14" /></filter>
          <filter id="grain" x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" />
            <feColorMatrix values="0 0 0 0 1  0 0 0 0 0.85  0 0 0 0 0.6  0 0 0 0.5 0" />
          </filter>
        </defs>

        <rect width="1600" height="900" fill="#140d0b" />
        <rect width="1600" height="900" fill="url(#glow)" />

        <g filter="url(#bokeh)" opacity="0.55">
          <circle cx="1480" cy="120" r="70" fill="#ffcf8a" opacity="0.25" />
          <circle cx="1330" cy="800" r="90" fill="#ff9a4d" opacity="0.2" />
          <circle cx="880" cy="90" r="55" fill="#ffd9a0" opacity="0.18" />
          <circle cx="1540" cy="520" r="60" fill="#ffb066" opacity="0.18" />
        </g>

        <g transform="translate(1130 470)" filter="url(#soft)">
          <circle r="385" fill="url(#rim)" />
          <circle r="360" fill="url(#plate)" />
          <circle r="250" fill="url(#sauce)" />
          <circle r="250" fill="none" stroke="#8a5a3a" strokeOpacity="0.35" strokeWidth="2" />

          <g transform="rotate(-18)">
            <rect x="-215" y="-95" width="430" height="190" rx="84" fill="url(#salmon)" />
            <g stroke="#ffd6ad" strokeOpacity="0.38" strokeWidth="5" strokeLinecap="round">
              <path d="M-160 -50 Q-60 -78 40 -52 T180 -40" fill="none" />
              <path d="M-170 -5 Q-60 -33 40 -8 T185 5" fill="none" />
              <path d="M-150 42 Q-50 18 50 40 T170 50" fill="none" />
            </g>
            <rect x="-215" y="-95" width="430" height="190" rx="84" fill="none" stroke="#fff" strokeOpacity="0.08" strokeWidth="3" />
          </g>

          <g>
            <ellipse cx="-230" cy="-120" rx="70" ry="30" fill="#4f7a2c" transform="rotate(-30 -230 -120)" />
            <ellipse cx="-200" cy="-140" rx="55" ry="22" fill="#6d9a3a" transform="rotate(20 -200 -140)" />
            <ellipse cx="-250" cy="30" rx="62" ry="26" fill="#355a1f" transform="rotate(12 -250 30)" />
            <ellipse cx="-185" cy="120" rx="68" ry="28" fill="#5f8c34" transform="rotate(-24 -185 120)" />
            <ellipse cx="215" cy="150" rx="64" ry="26" fill="#486f27" transform="rotate(35 215 150)" />
            <ellipse cx="250" cy="-110" rx="58" ry="24" fill="#7aa343" transform="rotate(-18 250 -110)" />
            <ellipse cx="60" cy="-200" rx="60" ry="24" fill="#3f6422" transform="rotate(8 60 -200)" />
          </g>

          <g>
            <rect x="-120" y="-170" width="34" height="34" rx="7" fill="#f0e2bd" transform="rotate(18 -103 -153)" />
            <rect x="-60" y="150" width="32" height="32" rx="7" fill="#e5803d" transform="rotate(-12 -44 166)" />
            <rect x="130" y="-165" width="30" height="30" rx="7" fill="#f0e2bd" transform="rotate(30 145 -150)" />
            <rect x="170" y="70" width="34" height="34" rx="7" fill="#9bb552" transform="rotate(-22 187 87)" />
            <rect x="-175" y="-45" width="28" height="28" rx="6" fill="#e5803d" transform="rotate(14 -161 -31)" />
            <rect x="20" y="130" width="30" height="30" rx="7" fill="#f0e2bd" transform="rotate(8 35 145)" />
            <rect x="-90" y="60" width="26" height="26" rx="6" fill="#9bb552" transform="rotate(-30 -77 73)" />
            <rect x="105" y="-20" width="24" height="24" rx="6" fill="#e5803d" transform="rotate(25 117 -8)" />
          </g>
        </g>

        <rect width="1600" height="900" filter="url(#grain)" opacity="0.07" />
      </svg>

      <img
        src="/hero.jpg"
        alt=""
        className="absolute inset-0 size-full object-cover"
        onError={(event) => {
          event.currentTarget.style.display = 'none'
        }}
      />
      <div className="absolute inset-0 bg-gradient-to-r from-night/95 via-night/70 to-night/10" />
      <div className="absolute inset-0 bg-gradient-to-t from-night via-transparent to-night/40" />
    </div>
  )
}
