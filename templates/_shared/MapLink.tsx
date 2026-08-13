import { FOCUS_RING } from "./focus";

type MapLinkProps = {
  address: string;
  mapsUrl: string;
  embedUrl?: string;
  className?: string;
  linkClassName?: string;
  iframeClassName?: string;
};

function safeHttpUrl(value: string | undefined): string | undefined {
  if (!value || value.includes("<") || /javascript:/i.test(value)) {
    return undefined;
  }
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return undefined;
    }
    return value;
  } catch {
    return undefined;
  }
}

export function MapLink({
  address,
  mapsUrl,
  embedUrl,
  className,
  linkClassName,
  iframeClassName,
}: MapLinkProps) {
  const href = safeHttpUrl(mapsUrl);
  const iframeSrc = safeHttpUrl(embedUrl);

  return (
    <div className={className}>
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className={`${FOCUS_RING} ${linkClassName ?? ""}`.trim()}
        >
          {address}
        </a>
      ) : (
        <p>{address}</p>
      )}
      {iframeSrc ? (
        <iframe
          title={address}
          src={iframeSrc}
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
          className={iframeClassName}
        />
      ) : null}
    </div>
  );
}
