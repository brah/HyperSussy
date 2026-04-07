import { memo } from "react";
import { Link } from "react-router-dom";
import { shortAddress } from "../../utils/format";

interface AddressLinkProps {
  address: string;
  label?: string | null;
  chars?: number;
}

export const AddressLink = memo(function AddressLink({ address, label, chars = 4 }: AddressLinkProps) {
  const display = label || shortAddress(address, chars);
  return (
    <Link
      to={`/wallets/${address}`}
      className="text-hs-green-dark hover:underline font-mono text-sm"
      title={address}
    >
      {display}
    </Link>
  );
});
