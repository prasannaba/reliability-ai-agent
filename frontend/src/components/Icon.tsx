import type { CSSProperties } from "react";
import {
  ArrowClockwise,
  ArrowLeft,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Display,
  Download,
  ExclamationTriangle,
  Gear,
  LayoutSidebar,
  List,
  Moon,
  Paperclip,
  Pencil,
  PencilSquare,
  Robot,
  Search,
  StopFill,
  Sun,
  Trash,
  X,
} from "react-bootstrap-icons";

const ICONS = {
  new_chat: PencilSquare,
  search: Search,
  delete: Trash,
  settings: Gear,
  menu: List,
  layout_sidebar: LayoutSidebar,
  smart_toy: Robot,
  expand_more: ChevronDown,
  check: Check,
  refresh: ArrowClockwise,
  content_copy: Clipboard,
  download: Download,
  edit: Pencil,
  warning: ExclamationTriangle,
  attach_file: Paperclip,
  stop: StopFill,
  arrow_upward: ArrowUp,
  arrow_back: ArrowLeft,
  chevron_right: ChevronRight,
  close: X,
  sun: Sun,
  moon: Moon,
  system: Display,
} as const;

export type IconName = keyof typeof ICONS;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  style?: CSSProperties;
}

/** Bootstrap-Icons equivalent of the old `<app-icon name="…">`. */
export function Icon({ name, size = 18, className, style }: IconProps) {
  const Cmp = ICONS[name];
  return (
    <Cmp size={size} className={className} style={style} aria-hidden="true" />
  );
}
