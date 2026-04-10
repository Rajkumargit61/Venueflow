import requests
from bs4 import BeautifulSoup

def get_live_cricket():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get('https://www.cricbuzz.com/cricket-match/live-scores', headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Cricbuzz live score class often is cb-mtch-crd-rt-col or similar, let's just grab the first match text
        matches = soup.find_all('div', class_='cb-mtch-blk')
        if not matches:
            return "No match div found"
            
        first_match = matches[0]
        teams = first_match.find_all('div', class_='cb-hm-rght') # or similar, let's just dump raw text
        return first_match.text[:200]
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    print("Scraping Result:", get_live_cricket())
