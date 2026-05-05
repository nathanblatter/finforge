interface HeaderProps {
  title: string
}

export default function Header({ title }: HeaderProps) {
  return <h1 className="text-xl font-semibold text-slate-100">{title}</h1>
}
