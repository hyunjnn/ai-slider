import { cn } from '@/lib/utils';
import { Tourney } from 'next/font/google';
import Link from 'next/link';

interface CustomLogoProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  withLink?: boolean;
  className?: string;
  text: string;
}

const tourney = Tourney({
  subsets: ['latin'],
  weight: ['400'],
  variable: '--font-pacifico',
});

const CustomLogo = ({ size = 'md', withLink = true, className, text }: CustomLogoProps) => {
  const sizeClasses = {
    sm: 'text-2xl md:text-3xl',
    md: 'text-3xl md:text-4xl',
    lg: 'text-4xl md:text-5xl lg:text-6xl',
    xl: 'text-4xl sm:text-5xl md:text-7xl lg:text-8xl',
  };

  const content = <h2 className={cn(sizeClasses[size], 'font-bold', tourney.className, className)}>{text}</h2>;

  if (withLink) {
    return <Link href="/">{content}</Link>;
  }

  return content;
};

export default CustomLogo;
