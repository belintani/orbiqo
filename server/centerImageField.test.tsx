// @vitest-environment jsdom

import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CenterImageField } from "../client/src/components/CenterImageField";

afterEach(cleanup);

describe("CenterImageField", () => {
  it("shows a normalized bridge preview and clears the supplied URL, preview, and error", () => {
    function Harness() {
      const [value, setValue] = useState("https://cdn.example.test/mark.png");
      const [cleared, setCleared] = useState(false);
      return <CenterImageField value={value} onChange={setValue} onClear={() => { setValue(""); setCleared(true); }} previewBase64={cleared ? undefined : "iVBORw0KGgo="} host={cleared ? undefined : "cdn.example.test"} error={cleared ? undefined : "The image could not be reached."} />;
    }

    render(<Harness />);
    expect(screen.getByTestId("center-image-preview")).toBeTruthy();
    expect(screen.getByAltText("Normalized center image preview")).toBeTruthy();
    expect(screen.getByText("cdn.example.test")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect((screen.getByRole("textbox", { name: /Center image URL/ }) as HTMLInputElement).value).toBe("");
    expect(screen.queryByTestId("center-image-preview")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reports non-HTTPS and bridge security errors next to the field", () => {
    const { rerender } = render(<CenterImageField value="http://example.test/mark.png" onChange={() => undefined} onClear={() => undefined} />);
    expect(screen.getByRole("alert").textContent).toBe("Use a public HTTPS image URL.");

    rerender(<CenterImageField value="https://127.0.0.1/mark.png" onChange={() => undefined} onClear={() => undefined} error="center image URL must resolve to a public address" />);
    expect(screen.getByRole("alert").textContent).toContain("must resolve to a public address");
  });

  it("reports an over-limit URL before a generation request", () => {
    render(<CenterImageField value={`https://images.example.test/${"a".repeat(2049)}`} onChange={() => undefined} onClear={() => undefined} />);
    expect(screen.getByRole("alert").textContent).toBe("Center image URLs must be 2,048 characters or fewer.");
  });

  it.each([
    ["The URL did not return a supported PNG, JPEG, or WebP image."],
    ["The image could not be reached. Check that the public HTTPS URL is available."],
  ])("renders a specific bridge failure message: %s", message => {
    render(<CenterImageField value="https://images.example.test/mark" onChange={() => undefined} onClear={() => undefined} error={message} />);
    expect(screen.getByRole("alert").textContent).toBe(message);
  });
});
