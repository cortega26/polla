"""Test prize parsing functionality."""

import pytest
from polla_app.scraper import PollaScraper
from polla_app.exceptions import ScriptError


class TestPrizeParser:
    """Test the prize parsing logic."""
    
    @pytest.fixture
    def scraper(self, app_config, mock_page, mock_logger):
        """Create scraper instance."""
        return PollaScraper(app_config, mock_page, mock_logger)
    
    def test_parse_simple_number(self, scraper):
        """Test parsing simple number."""
        assert scraper._parse_prize("1200000") == 1200000
    
    def test_parse_with_currency(self, scraper):
        """Test parsing with currency symbol."""
        assert scraper._parse_prize("$1.200.000") == 1200000
    
    def test_parse_with_commas(self, scraper):
        """Test parsing with comma separators."""
        assert scraper._parse_prize("$1,200,000") == 1200000
    
    def test_parse_millions_notation(self, scraper):
        """Test parsing MM (millions) notation."""
        assert scraper._parse_prize("1.2 MM") == 1200000
        assert scraper._parse_prize("1,2 MM") == 1200000
    
    def test_parse_small_number_assumption(self, scraper):
        """Test that small numbers are assumed to be in millions."""
        assert scraper._parse_prize("1.2") == 1200000
    
    def test_parse_zero(self, scraper):
        """Test parsing zero."""
        assert scraper._parse_prize("0") == 0
    
    def test_parse_empty_raises_error(self, scraper):
        """Test that empty string raises error."""
        with pytest.raises(ScriptError) as exc_info:
            scraper._parse_prize("")
        assert exc_info.value.error_code == "PRIZE_PARSING_ERROR"
    
    def test_parse_invalid_raises_error(self, scraper):
        """Test that invalid text raises error."""
        with pytest.raises(ScriptError) as exc_info:
            scraper._parse_prize("invalid")
        assert exc_info.value.error_code == "PRIZE_PARSING_ERROR"


class TestPrizeValidation:
    """Test prize validation logic."""
    
    @pytest.fixture
    def scraper(self, app_config, mock_page, mock_logger):
        """Create scraper instance."""
        return PollaScraper(app_config, mock_page, mock_logger)
    
    def test_validate_valid_prizes(self, scraper):
        """Test validation of valid prize list."""
        prizes = [1000000, 2000000, 500000, 300000, 1500000, 100000, 50000]
        scraper._validate_prizes(prizes)  # Should not raise
    
    def test_validate_empty_list(self, scraper):
        """Test validation of empty list."""
        with pytest.raises(ScriptError) as exc_info:
            scraper._validate_prizes([])
        assert exc_info.value.error_code == "NO_PRIZES_ERROR"
    
    def test_validate_insufficient_prizes(self, scraper):
        """Test validation with too few prizes."""
        with pytest.raises(ScriptError) as exc_info:
            scraper._validate_prizes([1000000, 2000000, 500000])
        assert exc_info.value.error_code == "INSUFFICIENT_PRIZES_ERROR"
    
    def test_validate_all_zeros(self, scraper):
        """Test validation with all zero prizes."""
        with pytest.raises(ScriptError) as exc_info:
            scraper._validate_prizes([0, 0, 0, 0, 0, 0, 0])
        assert exc_info.value.error_code == "ZERO_PRIZES_ERROR"
