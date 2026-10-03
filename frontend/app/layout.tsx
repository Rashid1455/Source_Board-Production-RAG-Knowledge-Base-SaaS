import type { Metadata } from 'next';
import './globals.css';
import AnimatedBackdrop from './animated-backdrop';
export const metadata: Metadata = {title:'Sourceboard — Company knowledge, grounded',description:'Ask questions of your company documents with traceable evidence.'};
export default function Layout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body><AnimatedBackdrop/>{children}</body></html>;
}
