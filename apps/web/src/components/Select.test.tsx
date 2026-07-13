import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Select } from "./Select";

describe("Select", () => {
  it("renders the selected option label", () => {
    const options = [
      { value: "a", label: "Alpha" },
      { value: "b", label: "Beta" },
    ];
    render(<Select value="b" onChange={() => {}} options={options} />);
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });
});
