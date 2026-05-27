import { useTranslation } from "react-i18next";
import { Position } from "../api";
import { Modal } from "../components/Modal";

export function DetailsModal({
  position,
  onClose,
}: {
  position: Position | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  if (!position) return null;
  const p = position;
  const ts = new Date(p.time_id);
  const rows: [string, React.ReactNode][] = [
    [t("detailsModal.timestamp"), <span className="mono">{ts.toLocaleString()}</span>],
    ...(p.speed != null ? [[t("detailsModal.speed"), <span>{p.speed.toFixed(2)} km/h</span>] as [string, React.ReactNode]] : []),
    ...(p.altitude != null ? [[t("detailsModal.altitude"), <span>{p.altitude.toFixed(1)} m</span>] as [string, React.ReactNode]] : []),
    ...(p.satellites != null ? [[t("detailsModal.satellites"), <span>{p.satellites}</span>] as [string, React.ReactNode]] : []),
  ];
  return (
    <Modal
      open
      onClose={onClose}
      title={t("detailsModal.title")}
      footer={<button className="primary" onClick={onClose}>{t("common.close")}</button>}
    >
      <table className="kv">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}><th>{k}</th><td>{v}</td></tr>
          ))}
        </tbody>
      </table>
    </Modal>
  );
}
