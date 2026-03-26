interface PageHeaderProps {
  title: string;
  children?: React.ReactNode;
}

export function PageHeader({ title, children }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-6">
      <h1 className="text-xl font-semibold text-[#fafafa]">{title}</h1>
      {children && <div className="flex items-center gap-3">{children}</div>}
    </div>
  );
}
