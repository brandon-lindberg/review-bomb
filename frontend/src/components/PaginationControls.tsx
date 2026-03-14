import Link from "next/link";

interface PaginationControlsProps {
  page: number;
  totalPages: number;
  buildHref: (page: number) => string;
}

export function PaginationControls({
  page,
  totalPages,
  buildHref,
}: PaginationControlsProps) {
  if (totalPages <= 1) {
    return null;
  }

  return (
    <nav className="site-pagination" aria-label="Pagination">
      {page > 1 ? (
        <Link href={buildHref(page - 1)} className="site-pagination__link">
          Previous
        </Link>
      ) : (
        <span className="site-pagination__link site-pagination__link--disabled">
          Previous
        </span>
      )}

      <span className="site-pagination__status">
        Page {page} of {totalPages}
      </span>

      {page < totalPages ? (
        <Link href={buildHref(page + 1)} className="site-pagination__link">
          Next
        </Link>
      ) : (
        <span className="site-pagination__link site-pagination__link--disabled">
          Next
        </span>
      )}
    </nav>
  );
}
