import React from "react";
import {
  CircleDot, Contrast, Droplet, DropletOff, Droplets, Eye, Feather, Grip, Hourglass, Layers,
  ShieldPlus, Sparkles, Sun, Umbrella, Waves, Zap,
} from "lucide-react";

/*
 * Each concern has its own soft colour, the way health apps colour-code
 * categories, so a grid of fifteen reads at a glance. [background, ink] pairs
 * are muted to sit with the porcelain and rosewood palette; every ink passes
 * 4.5:1 on its own background.
 */
const HUES = {
  sage: ["#E6EFE6", "#43704F"],
  caramel: ["#F5EAD8", "#87601F"],
  plum: ["#F0E5EE", "#774C70"],
  rose: ["#F5E4DE", "#8F4F3B"],
  sand: ["#F2EADF", "#7A5D37"],
  coral: ["#F9E4E0", "#A44A3F"],
  mist: ["#E2EDF2", "#386780"],
  taupe: ["#ECE8E2", "#5F5850"],
  gold: ["#F8EED5", "#8A6418"],
  terracotta: ["#F5E3D9", "#9A502E"],
  lavender: ["#E9E7F3", "#545189"],
  sun: ["#FBEFCF", "#8A6210"],
  ember: ["#F7E2D8", "#A44E28"],
  honey: ["#F8EBD6", "#8E5B19"],
  teal: ["#E0EFEC", "#36706A"],
};

// duo: the icon is made of closed shapes, so it can take a soft fill.
const CONCERNS = {
  "Acne & Oily Skin": { icon: Droplet, hue: "sage", duo: true },
  "Pigmentation": { icon: Contrast, hue: "caramel", duo: true },
  "Aging & Fine Lines": { icon: Hourglass, hue: "plum", duo: true },
  "Barrier Repair": { icon: ShieldPlus, hue: "rose", duo: true },
  "Dry Skin": { icon: DropletOff, hue: "sand" },
  "Sensitive Skin": { icon: Feather, hue: "coral" },
  "Hydration": { icon: Droplets, hue: "mist", duo: true },
  "Large Pores": { icon: Grip, hue: "taupe", duo: true },
  "Dullness": { icon: Sparkles, hue: "gold", duo: true },
  "Uneven Texture": { icon: Layers, hue: "terracotta" },
  "Dark Circles": { icon: Eye, hue: "lavender", duo: true },
  "Sun Protection": { icon: Umbrella, hue: "sun" },
  "UV Damage": { icon: Zap, hue: "ember", duo: true },
  "Tanning": { icon: Sun, hue: "honey", duo: true },
  "Puffiness": { icon: Waves, hue: "teal" },
};

const FALLBACK = { icon: CircleDot, hue: "taupe" };

export function concernIcon(name) {
  return (CONCERNS[name] || FALLBACK).icon;
}

/** The concern's icon on its own coloured tile. Decorative: the name is always shown beside it. */
export function ConcernBadge({ name, size = "md", className = "" }) {
  const { icon: Icon, hue, duo } = CONCERNS[name] || FALLBACK;
  const [bg, ink] = HUES[hue];
  return (
    <span className={`cbadge cbadge--${size} ${className}`.trim()} aria-hidden="true"
          style={{ "--cb-bg": bg, "--cb-ink": ink }}>
      <Icon strokeWidth={1.75} {...(duo ? { fill: "currentColor", fillOpacity: 0.2 } : {})} />
    </span>
  );
}
