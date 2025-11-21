# Off Book Website

This is the landing page for offbook.ca, hosted on GitHub Pages.

## Setup for GitHub Pages

1. Push this `website` folder to your GitHub repository
2. Go to your repository settings on GitHub
3. Navigate to "Pages" in the left sidebar
4. Under "Source", select the branch and folder (usually `main` branch and `/website` folder)
5. Your site will be available at `https://[your-username].github.io/[repository-name]/` or configure a custom domain

## Custom Domain Setup

To use `offbook.ca`:

1. In your repository's Pages settings, add `offbook.ca` as a custom domain
2. Add a `CNAME` file in the website folder with the content: `offbook.ca`
3. Configure your DNS settings with your domain provider:
   - Add a CNAME record pointing to `[your-username].github.io`
   - Or add A records pointing to GitHub's IP addresses (check GitHub Pages documentation for current IPs)

## Customization

Edit `index.html` to fill in:
- Hero section tagline
- About section content
- Feature descriptions
- Any other content you want to add

Edit `styles.css` to customize colors, fonts, and styling.

