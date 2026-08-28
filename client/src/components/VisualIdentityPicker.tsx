import React from "react";
import type { OrbiqoIdentityId, OrbiqoVisualIdentity } from "@shared/orbiqo";
import { Check, LoaderCircle } from "lucide-react";

type VisualIdentityPickerProps = {
  identities?: OrbiqoVisualIdentity[];
  loading: boolean;
  selectedId: OrbiqoIdentityId;
  onSelect: (identityId: OrbiqoIdentityId) => void;
};

export function VisualIdentityPicker({ identities, loading, selectedId, onSelect }: VisualIdentityPickerProps) {
  return (
    <div className="identity-template-grid" role="radiogroup" aria-label="Visual identity templates">
      {loading ? (
        <div className="identity-loading"><LoaderCircle className="animate-spin" size={15} /> Loading validated templates…</div>
      ) : identities?.map(identity => (
        <button
          aria-checked={selectedId === identity.id}
          className={`identity-template-card ${selectedId === identity.id ? "is-active" : ""}`}
          key={identity.id}
          onClick={() => onSelect(identity.id)}
          role="radio"
          type="button"
        >
          <span className="identity-card-topline">
            <span className="identity-palette" aria-label={`${identity.name} palette`}>
              {identity.colors.map(color => <i key={color} style={{ backgroundColor: color }} />)}
            </span>
            <span className="identity-validation"><Check size={11} /> Validated</span>
          </span>
          <span className="identity-card-copy"><strong>{identity.name}</strong><small>{identity.description}</small></span>
          <span className="identity-card-profile"><span>{identity.tone}</span><span>{identity.visual_style} profile</span></span>
          <span className="identity-card-meta"><span>{identity.palette_name}</span><span>Registered · v{identity.format_version}</span></span>
        </button>
      ))}
    </div>
  );
}
