import { Link } from "react-router-dom";

interface CoinLinkProps {
  coin: string;
  className?: string;
}

/** Inline coin name that navigates to that coin's analytics view. */
export function CoinLink({ coin, className }: Readonly<CoinLinkProps>) {
  return (
    <Link
      to={`/?coin=${coin}`}
      className={
        className ?? "text-hs-text hover:text-hs-teal hover:underline font-medium"
      }
    >
      {coin}
    </Link>
  );
}
