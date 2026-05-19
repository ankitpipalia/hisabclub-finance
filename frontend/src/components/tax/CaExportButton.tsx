/**
 * CaExportButton — Sprint B.5/B.6.
 *
 * Fetches GET /api/v1/tax/export/ca-pack/{fy} as a Blob and triggers a
 * browser download. No external dependency.
 */

import { useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '../../api/client';
import { useToast } from '../ui/Toast';

type Props = {
  fy: string;
};

export default function CaExportButton({ fy }: Props) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const handleDownload = async () => {
    setBusy(true);
    try {
      const blob = await api.downloadCaPack(fy);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `hisabclub_capack_${fy}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success(`CA pack for ${fy} ready`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not generate CA pack');
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleDownload()}
      disabled={busy}
      className="hc-btn hc-btn-solid"
      data-testid="ca-export-button"
    >
      <Download size={14} strokeWidth={1.5} />
      {busy ? 'Generating…' : 'CA hand-off pack'}
    </button>
  );
}
