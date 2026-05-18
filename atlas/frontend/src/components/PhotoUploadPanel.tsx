import { useState } from "react";
import {
  GripVertical,
  ImageOff,
  ImagePlus,
  Loader2,
  MapPin,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  api,
  useDeleteEdgePhoto,
  useDeleteNodePhoto,
  useEdgePhotos,
  useGenerateFromPhotos,
  useNodePhotos,
  useReorderEdgePhotos,
  useReorderNodePhotos,
  useUpdateEdgePhotoCaption,
  useUpdateNodePhotoCaption,
  useUploadEdgePhoto,
  useUploadNodePhoto,
  type EdgePhoto,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** Subject the photos attach to. Edges drive vision generation; nodes don't. */
type PhotoSubject =
  | { kind: "edge"; slug: string; fromId: string; toId: string }
  | { kind: "node"; slug: string; nodeId: string };

interface Props {
  subject: PhotoSubject;
  /** Called after a successful generate (edges only). */
  onGenerated?: () => void;
}

const MAX_PHOTOS = 10;
const MIN_TO_GENERATE = 2;

/**
 * Editor-only panel for uploading photos against an edge or a node, reordering
 * them, captioning them, and (for edges only) triggering vision-model
 * generation.
 *
 * The component keeps a single rendered shape but switches its underlying
 * hooks based on `subject.kind`. Node photos are reviewer-reference only;
 * the consent block stays on (privacy/IP concerns are identical) but the
 * Generate button is hidden.
 *
 * See docs/29-photo-edge-walker.md and the redesign mockup at
 * docs/30-editor-redesign-mockup.html.
 */
export function PhotoUploadPanel({ subject, onGenerated }: Props) {
  const isEdge = subject.kind === "edge";
  const slug = subject.slug;

  // Branch the hooks by subject kind. Both branches always evaluate so the
  // rules of hooks aren't violated; the disabled branch's queries no-op via
  // their `enabled` flag.
  const edgePhotos = useEdgePhotos(
    isEdge ? slug : null,
    isEdge ? subject.fromId : null,
    isEdge ? subject.toId : null,
  );
  const nodePhotos = useNodePhotos(
    !isEdge ? slug : null,
    !isEdge ? subject.nodeId : null,
  );

  const uploadEdge = useUploadEdgePhoto();
  const uploadNode = useUploadNodePhoto();
  const reorderEdge = useReorderEdgePhotos();
  const reorderNode = useReorderNodePhotos();
  const captionEdge = useUpdateEdgePhotoCaption();
  const captionNode = useUpdateNodePhotoCaption();
  const deleteEdge = useDeleteEdgePhoto();
  const deleteNode = useDeleteNodePhoto();
  const generate = useGenerateFromPhotos();

  const photos = isEdge ? edgePhotos : nodePhotos;
  const upload = isEdge ? uploadEdge : uploadNode;
  const reorder = isEdge ? reorderEdge : reorderNode;
  // captionEdge/captionNode and deleteEdge/deleteNode are dispatched
  // explicitly inside the handlers below — no shared alias needed here.

  const [consent, setConsent] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingCaption, setPendingCaption] = useState("");
  const [draggingId, setDraggingId] = useState<string | null>(null);

  const list = photos.data?.photos ?? [];
  const inFlight = upload.isPending || reorder.isPending || generate.isPending;
  const canGenerate = isEdge && list.length >= MIN_TO_GENERATE && consent && !inFlight;
  const canUpload = list.length < MAX_PHOTOS && consent && !inFlight && !!pendingFile;
  const gpsCount = list.filter((p) => p.lat != null && p.lng != null).length;

  const dispatchUpload = (file: File, caption: string | null) => {
    if (subject.kind === "edge") {
      return uploadEdge.mutateAsync({
        slug, fromId: subject.fromId, toId: subject.toId,
        file, caption, consent: true,
      });
    }
    return uploadNode.mutateAsync({
      slug, nodeId: subject.nodeId, file, caption, consent: true,
    });
  };
  const dispatchReorder = (photoIds: string[]) => {
    if (subject.kind === "edge") {
      return reorderEdge.mutate({ slug, fromId: subject.fromId, toId: subject.toId, photoIds });
    }
    return reorderNode.mutate({ slug, nodeId: subject.nodeId, photoIds });
  };
  const dispatchCaption = (photoId: string, caption: string | null) => {
    if (subject.kind === "edge") {
      return captionEdge.mutate({ slug, fromId: subject.fromId, toId: subject.toId, photoId, caption });
    }
    return captionNode.mutate({ slug, nodeId: subject.nodeId, photoId, caption });
  };
  const dispatchDelete = (photoId: string) => {
    if (subject.kind === "edge") {
      return deleteEdge.mutate({ slug, fromId: subject.fromId, toId: subject.toId, photoId });
    }
    return deleteNode.mutate({ slug, nodeId: subject.nodeId, photoId });
  };

  const submitUpload = async () => {
    if (!pendingFile || !consent) return;
    try {
      await dispatchUpload(pendingFile, pendingCaption.trim() || null);
      setPendingFile(null);
      setPendingCaption("");
    } catch {
      // Error surfaces in upload.error below.
    }
  };

  const onDrop = (targetId: string) => {
    if (!draggingId || draggingId === targetId) return;
    const ids = list.map((p) => p.id);
    const fromIdx = ids.indexOf(draggingId);
    const toIdx = ids.indexOf(targetId);
    if (fromIdx < 0 || toIdx < 0) return;
    ids.splice(toIdx, 0, ids.splice(fromIdx, 1)[0]);
    dispatchReorder(ids);
    setDraggingId(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-2">
        <span className="ff-mono text-[10px] tracking-wide-2 text-slate-2">
          {list.length}/{MAX_PHOTOS}
          {gpsCount > 0 && <> · {gpsCount} GPS</>}
        </span>
      </div>

      <p className="text-[12px] text-ink-2 leading-relaxed">
        {isEdge
          ? "Upload photos walking from the start node to the end node, in order. EXIF GPS is used to draft a polyline; captions anchor the model."
          : "Reviewer reference only. Photos do not ship to the patient app — they help the next editor see what this place looks like."}
      </p>

      {list.length > 0 && (
        <ul className="space-y-1.5">
          {list.map((p, i) => (
            <PhotoRow
              key={p.id}
              photo={p}
              index={i}
              slug={slug}
              isDragging={draggingId === p.id}
              onDragStart={() => setDraggingId(p.id)}
              onDragEnd={() => setDraggingId(null)}
              onDropOn={() => onDrop(p.id)}
              onCaptionChange={(caption) => dispatchCaption(p.id, caption)}
              onDelete={() => dispatchDelete(p.id)}
            />
          ))}
        </ul>
      )}

      {list.length < MAX_PHOTOS && (
        <div className="border border-hairline rounded-sm p-3 bg-paper-2 space-y-2">
          <div className="flex items-center gap-2">
            <input
              type="file"
              accept="image/jpeg,image/heic,image/heif"
              onChange={(e) => setPendingFile(e.target.files?.[0] ?? null)}
              className="text-[11.5px] flex-1 ff-mono text-slate"
            />
            {pendingFile && (
              <span className="text-[10.5px] ff-mono text-slate-2">
                {(pendingFile.size / 1024 / 1024).toFixed(1)} MB
              </span>
            )}
          </div>
          <input
            type="text"
            value={pendingCaption}
            onChange={(e) => setPendingCaption(e.target.value)}
            placeholder={isEdge ? "Optional caption (e.g. lobby with elevator bank)" : "Optional caption"}
            maxLength={500}
            className="w-full bg-paper border border-hairline rounded-sm px-2 h-8 text-[12px] outline-none focus:border-saffron"
          />
          <button
            onClick={submitUpload}
            disabled={!canUpload}
            className={cn(
              "w-full h-8 rounded-sm text-[11px] tracking-wide-2 small-caps flex items-center justify-center gap-1.5 transition-colors",
              canUpload
                ? "bg-ink text-paper hover:bg-ink-2"
                : "bg-paper text-slate-2 border border-hairline cursor-not-allowed",
            )}
          >
            {upload.isPending ? (
              <Loader2 size={11} className="animate-spin" strokeWidth={1.5} />
            ) : (
              <ImagePlus size={11} strokeWidth={1.5} />
            )}
            Upload photo
          </button>
        </div>
      )}

      <label className="flex items-start gap-2 text-[11.5px] cursor-pointer select-none">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-0.5 accent-saffron"
        />
        <span className="text-ink-2 leading-snug">
          I have the right to share these photos and grant the project a
          license to use them for wayfinding.
        </span>
      </label>

      {upload.isError && (
        <p className="ff-mono text-[10.5px] text-rust">
          {(upload.error as Error)?.message}
        </p>
      )}
      {generate.isError && (
        <p className="ff-mono text-[10.5px] text-rust">
          {(generate.error as Error)?.message}
        </p>
      )}

      {isEdge && (
        <>
          <button
            onClick={() => {
              if (subject.kind !== "edge") return;
              generate.mutate(
                { slug, fromId: subject.fromId, toId: subject.toId },
                { onSuccess: () => onGenerated?.() },
              );
            }}
            disabled={!canGenerate}
            className={cn(
              "w-full h-9 rounded-sm text-[11.5px] tracking-wide-2 small-caps flex items-center justify-center gap-2 transition-colors",
              canGenerate
                ? "bg-saffron text-paper hover:bg-saff-2"
                : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
            )}
          >
            {generate.isPending ? (
              <Loader2 size={12} className="animate-spin" strokeWidth={1.5} />
            ) : (
              <Sparkles size={12} strokeWidth={1.5} />
            )}
            Draft instruction from photos
          </button>

          {list.length < MIN_TO_GENERATE && (
            <p className="ff-mono text-[10.5px] text-slate-2 text-center">
              Upload at least {MIN_TO_GENERATE} photos to generate.
            </p>
          )}
        </>
      )}
    </div>
  );
}

interface PhotoRowProps {
  photo: EdgePhoto;
  index: number;
  slug: string;
  isDragging: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDropOn: () => void;
  onCaptionChange: (caption: string | null) => void;
  onDelete: () => void;
}

function PhotoRow({
  photo, index, slug, isDragging, onDragStart, onDragEnd, onDropOn,
  onCaptionChange, onDelete,
}: PhotoRowProps) {
  const [caption, setCaption] = useState(photo.caption ?? "");
  const hasGps = photo.lat != null && photo.lng != null;

  return (
    <li
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDropOn}
      className={cn(
        "flex items-start gap-2 border border-hairline rounded-sm p-2 bg-paper transition-opacity",
        isDragging && "opacity-40",
      )}
    >
      <div className="flex flex-col items-center gap-1 pt-1">
        <GripVertical size={12} className="text-slate-2 cursor-grab" strokeWidth={1.5} />
        <span className="ff-mono text-[9px] text-slate-2">{index + 1}</span>
      </div>
      <img
        src={api.photoUrl(slug, photo.id)}
        alt={photo.original_filename}
        className="w-14 h-14 object-cover rounded-sm border border-hairline flex-shrink-0"
        loading="lazy"
      />
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          {hasGps ? (
            <span className="ff-mono text-[9.5px] tracking-wide-2 small-caps text-moss flex items-center gap-1">
              <MapPin size={9} strokeWidth={1.5} /> GPS
            </span>
          ) : (
            <span className="ff-mono text-[9.5px] tracking-wide-2 small-caps text-slate-2 flex items-center gap-1">
              <ImageOff size={9} strokeWidth={1.5} /> no GPS
            </span>
          )}
          <span className="ff-mono text-[9.5px] text-slate-2 truncate flex-1">
            {photo.original_filename}
          </span>
        </div>
        <input
          type="text"
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          onBlur={() => {
            if ((caption.trim() || null) !== photo.caption) {
              onCaptionChange(caption.trim() || null);
            }
          }}
          placeholder="caption (optional)"
          maxLength={500}
          className="w-full bg-paper-2 border border-hairline rounded-sm px-2 h-7 text-[11.5px] outline-none focus:border-saffron"
        />
      </div>
      <button
        onClick={onDelete}
        className="text-slate-2 hover:text-rust flex-shrink-0 pt-1"
        aria-label="Delete photo"
      >
        <Trash2 size={12} strokeWidth={1.5} />
      </button>
    </li>
  );
}
