export default function AppLogo({ size = 24, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      role="img"
      aria-label="HisabClub"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="8" y="8" width="104" height="104" stroke="currentColor" strokeWidth="8" />
      <path d="M28 34V86" stroke="currentColor" strokeWidth="8" />
      <path d="M28 60H58" stroke="currentColor" strokeWidth="8" />
      <path d="M58 34V86" stroke="#FF3D00" strokeWidth="8" />
      <path d="M90 34H68V86H90" stroke="#FF3D00" strokeWidth="8" />
    </svg>
  );
}
