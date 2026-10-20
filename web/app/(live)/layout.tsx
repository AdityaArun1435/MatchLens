import { SiteFooter } from "@/components/live/SiteNav";

export default function LiveLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <SiteFooter />
    </>
  );
}
