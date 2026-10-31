import { cx } from './ui'

// Positions in the cell, top to bottom, left column then right: standard dot numbers.
const LAYOUT = [
  [1, 4],
  [2, 5],
  [3, 6],
]

const sizes = {
  xl: { dot: 'size-14 sm:size-16', gap: 'gap-x-7 gap-y-5 sm:gap-x-8 sm:gap-y-6', pad: 'p-6 sm:p-7', num: 'text-xs' },
  lg: { dot: 'size-10', gap: 'gap-x-5 gap-y-3.5', pad: 'p-5', num: 'text-[10px]' },
  sm: { dot: 'size-2.5', gap: 'gap-x-1.5 gap-y-1', pad: 'p-2', num: '' },
  xs: { dot: 'size-1.5', gap: 'gap-x-1 gap-y-[3px]', pad: 'p-1.5', num: '' },
}

/**
 * A 6-dot braille cell. `mask` bit n-1 = dot n raised.
 * `rest` draws the idle state (all solenoids off) muted instead of as a character.
 * `pinLabels[d-1]` is the number printed on the pin at braille dot d's position
 * (the hardware's own numbering); without it, braille dot numbers are shown.
 */
export function BrailleCell({
  mask, size = 'lg', active, rest, numbers, label, pinLabels,
}: {
  mask: number
  size?: keyof typeof sizes
  active?: boolean
  rest?: boolean
  numbers?: boolean
  label?: string
  pinLabels?: number[]
}) {
  const s = sizes[size]
  const dots = LAYOUT.flat().filter((d) => mask & (1 << (d - 1)))
  return (
    <div
      role="img"
      aria-label={label ?? (dots.length ? `Braille dots ${dots.join(', ')}` : 'Blank braille cell')}
      className={cx(
        'inline-grid grid-cols-2 rounded-2xl border transition-colors',
        s.gap, s.pad,
        active ? 'border-accent/60 bg-accent/[0.06]' : 'border-line bg-bg/50',
        size === 'sm' || size === 'xs' ? 'rounded-lg' : '',
      )}
    >
      {LAYOUT.flat().map((dot) => {
        const raised = Boolean(mask & (1 << (dot - 1)))
        return (
          <span
            key={`${dot}-${raised}`}
            className={cx(
              'relative grid place-items-center rounded-full transition-all duration-150',
              s.dot,
              raised && !rest && 'animate-pop bg-[radial-gradient(circle_at_35%_30%,#b9fff1,var(--color-accent)_45%,#13a58c)] shadow-[0_0_18px_-2px] shadow-accent/70',
              raised && rest && 'bg-[radial-gradient(circle_at_35%_30%,#7d8aa3,#4a5670)] shadow-none',
              !raised && 'bg-[#060a12] shadow-[inset_0_2px_4px_rgb(0_0_0/0.9),inset_0_-1px_0_rgb(255_255_255/0.05)]',
            )}
          >
            {numbers && s.num && (
              <span className={cx('font-display font-semibold', s.num, raised && !rest ? 'text-accent-ink' : 'text-faint')}>
                {pinLabels?.[dot - 1] ?? dot}
              </span>
            )}
          </span>
        )
      })}
    </div>
  )
}
