import { Link } from "react-router-dom";
import { shortAddress } from "../../utils/format";

interface AddressLinkProps {
  address: string;
  label?: string | null;
  width?: number;
}

export function AddressLink({ address, label, width = 10 }: AddressLinkProps) {
  const display = label || shortAddress(address, width);
  return (
    <Link
      to={`/wallets/${address}`}
      className="text-hs-green-dark hover:underline font-mono text-sm"
      title={address}
    >
      {display}
    </Link>
  );
}
