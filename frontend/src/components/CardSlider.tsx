import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ImageIcon } from "lucide-react";

/** Photo carousel for a listing card. Lives inside the card's <Link>, so controls stop the click. */
export default function CardSlider({ photos }: { photos: string[] }) {
  const [idx, setIdx] = useState(0);
  const touchX = useRef<number | null>(null);
  const swiped = useRef(false);
  const n = photos.length;

  // Preload neighbours so flicking through feels instant.
  useEffect(() => {
    if (n < 2) return;
    for (const i of [idx + 1, idx - 1]) new Image().src = photos[(i + n) % n];
  }, [idx, n, photos]);

  if (!n) {
    return (
      <div className="noimg">
        <ImageIcon />
      </div>
    );
  }

  const go = (e: React.MouseEvent | null, step: number) => {
    e?.preventDefault();
    e?.stopPropagation();
    setIdx((i) => (i + step + n) % n);
  };

  return (
    <div
      className="slider"
      onTouchStart={(e) => {
        touchX.current = e.touches[0].clientX;
        swiped.current = false;
      }}
      onTouchEnd={(e) => {
        if (touchX.current == null) return;
        const dx = e.changedTouches[0].clientX - touchX.current;
        touchX.current = null;
        if (Math.abs(dx) > 40) {
          swiped.current = true;
          go(null, dx < 0 ? 1 : -1);
        }
      }}
      onClickCapture={(e) => {
        // A swipe ends with a click on touch devices; don't open the listing for it.
        if (swiped.current) {
          e.preventDefault();
          swiped.current = false;
        }
      }}
    >
      <img src={photos[idx]} alt="" loading={idx === 0 ? "lazy" : "eager"} draggable={false} />
      {n > 1 && (
        <>
          <button className="slide-nav prev" aria-label="Previous photo" onClick={(e) => go(e, -1)}>
            <ChevronLeft size={20} />
          </button>
          <button className="slide-nav next" aria-label="Next photo" onClick={(e) => go(e, 1)}>
            <ChevronRight size={20} />
          </button>
          <span className="count">
            {idx + 1} / {n}
          </span>
        </>
      )}
    </div>
  );
}
