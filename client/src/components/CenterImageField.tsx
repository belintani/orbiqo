import React from "react";

type CenterImageFieldProps = {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  previewBase64?: string | null;
  host?: string | null;
  error?: string | null;
};

function clientUrlError(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.length > 2048) return "Center image URLs must be 2,048 characters or fewer.";
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === "https:" ? null : "Use a public HTTPS image URL.";
  } catch {
    return "Enter a complete public HTTPS image URL.";
  }
}

export function CenterImageField({ value, onChange, onClear, previewBase64, host, error }: CenterImageFieldProps) {
  const validationError = clientUrlError(value);
  const visibleError = validationError ?? error ?? null;

  return (
    <div className={`center-image-field ${visibleError ? "is-error" : ""}`}>
      <label className="field-label" htmlFor="center-image-url"><span>Center image URL</span><small>HTTPS · optional</small></label>
      <div className="center-image-input-row">
        <input
          id="center-image-url"
          className="lab-input"
          type="url"
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder="https://example.com/mark.png"
          aria-describedby="center-image-help center-image-status"
          aria-invalid={Boolean(visibleError)}
        />
        {value ? <button type="button" onClick={onClear}>Clear</button> : null}
      </div>
      {previewBase64 ? (
        <div className="center-image-preview" data-testid="center-image-preview">
          <img src={`data:image/png;base64,${previewBase64}`} alt="Normalized center image preview" />
          <span><strong>Prepared by bridge</strong><small>{host ?? "public HTTPS source"}</small></span>
        </div>
      ) : null}
      <p id="center-image-help">A public HTTPS image is cropped into the non-functional center circle when you generate. It replaces the center mark.</p>
      {visibleError ? <p id="center-image-status" className="center-image-error" role="alert">{visibleError}</p> : null}
    </div>
  );
}
