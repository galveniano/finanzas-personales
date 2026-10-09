/** La marca de la app: el mismo trazo que el favicon y los iconos de la pantalla de inicio (public/icono.svg). */
export default function Logo({ grande }: { grande?: boolean }) {
  return (
    <div className={`grid place-items-center bg-accent text-panel ${grande ? 'size-12 rounded-xl' : 'size-8 rounded-lg'}`} aria-hidden>
      <svg viewBox="0 0 32 32" className={grande ? 'size-7' : 'size-5'} fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M7 22l6-7 5 3.5 7-9" />
      </svg>
    </div>
  )
}
