import Button from 'react-bootstrap/Button';
import Modal from 'react-bootstrap/Modal';
import { Icon } from './Icon';

interface ConfirmDialogProps {
  show: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Professional replacement for window.confirm for destructive actions. */
export function ConfirmDialog({
  show,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal show={show} onHide={onCancel} centered aria-label={title}>
      <Modal.Header closeButton>
        <Modal.Title className="d-flex align-items-center gap-2">
          <Icon name="warning" size={16} className="text-warning" />
          {title}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>{message}</Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} autoFocus>
          {confirmLabel}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
