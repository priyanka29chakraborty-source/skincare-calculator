#!/usr/bin/env python3
"""
Backend API Testing Suite for Skincare Worth Calculator
Tests all API endpoints and scoring logic according to blueprint specifications
"""

import requests
import json
import sys
from datetime import datetime

# Use the public API endpoint
API_BASE = "http://localhost:8001/api"

class SkincareAPITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, passed, details=""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"  Details: {details}")
        
        self.test_results.append({
            "name": name,
            "passed": passed,
            "details": details
        })

    def test_health_endpoint(self):
        """Test /api/health endpoint returns correct status"""
        try:
            response = requests.get(f"{API_BASE}/health", timeout=10)
            data = response.json()
            
            # Check status code
            if response.status_code != 200:
                self.log_test("Health Endpoint Status", False, f"Expected 200, got {response.status_code}")
                return False
            
            # Check required fields
            has_status = 'status' in data and data['status'] == 'alive'
            has_db_loaded = 'db_loaded' in data
            
            if has_status and has_db_loaded:
                self.log_test("Health Endpoint Response", True, f"Status: {data['status']}, DB Loaded: {data['db_loaded']}")
                return True
            else:
                self.log_test("Health Endpoint Response", False, f"Missing required fields. Got: {data}")
                return False
                
        except Exception as e:
            self.log_test("Health Endpoint Connection", False, f"Error: {str(e)}")
            return False

    def test_analyze_basic(self):
        """Test basic /api/analyze endpoint functionality"""
        test_payload = {
            "ingredients": "Aqua, Niacinamide, Glycerin, Sodium Hyaluronate, Panthenol",
            "price": 349,
            "size_ml": 30,
            "category": "Serum",
            "skin_concerns": ["Acne & Oily Skin", "Large Pores"],
            "skin_type": "oily",
            "country": "India"
        }
        
        try:
            response = requests.post(f"{API_BASE}/analyze", json=test_payload, timeout=30)
            
            if response.status_code != 200:
                self.log_test("Analyze Endpoint Basic", False, f"Status code: {response.status_code}, Response: {response.text}")
                return False
                
            data = response.json()
            
            # Check required fields exist
            required_fields = [
                'main_worth_score', 'main_worth_tier', 'component_scores',
                'component_details', 'skin_concern_fit', 'skin_type_compatibility',
                'identified_actives', 'price_analysis'
            ]
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                self.log_test("Analyze Response Structure", False, f"Missing fields: {missing_fields}")
                return False
            
            # Check component scores structure (A,B,C,D,E)
            component_scores = data['component_scores']
            expected_components = ['A', 'B', 'C', 'D', 'E']
            has_all_components = all(comp in component_scores for comp in expected_components)
            
            if not has_all_components:
                self.log_test("Component Scores Structure", False, f"Missing components in: {component_scores}")
                return False
                
            self.log_test("Analyze Endpoint Basic", True, f"Score: {data['main_worth_score']}, Tier: {data['main_worth_tier']}")
            return True
            
        except Exception as e:
            self.log_test("Analyze Endpoint Basic", False, f"Error: {str(e)}")
            return False

    def test_tier_labels(self):
        """Test that tier labels match blueprint specifications"""
        # Test different score ranges by manipulating ingredient lists
        test_cases = [
            {
                "name": "High Score Test (Expected: Worth Buying or Exceptional Value)",
                "ingredients": "Aqua, Niacinamide, Retinol, Ascorbic Acid, Peptides, Ceramide, Glycerin, Sodium Hyaluronate, Panthenol",
                "price": 200,
                "size_ml": 30,
                "expected_tier_options": ["Worth Buying", "Exceptional Value"]
            },
            {
                "name": "Mid Score Test (Expected: Acceptable but Overpriced)",
                "ingredients": "Aqua, Parfum, Alcohol Denat, Glycerin",
                "price": 800,  # High price for basic ingredients
                "size_ml": 30,
                "expected_tier_options": ["Acceptable but Overpriced", "Poor Value"]
            },
            {
                "name": "Low Score Test (Expected: Poor Value or Marketing-Driven Product)",  
                "ingredients": "Aqua, Parfum, Alcohol Denat, Essential Oil, Limonene",
                "price": 1200,  # Very high price for poor ingredients
                "size_ml": 30,
                "expected_tier_options": ["Poor Value", "Marketing-Driven Product"]
            }
        ]
        
        for test_case in test_cases:
            try:
                payload = {
                    "ingredients": test_case["ingredients"],
                    "price": test_case["price"],
                    "size_ml": test_case["size_ml"],
                    "category": "Serum",
                    "skin_concerns": ["Hydration"],
                    "skin_type": "normal",
                    "country": "India"
                }
                
                response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    tier = data.get('main_worth_tier', '')
                    score = data.get('main_worth_score', 0)
                    
                    # Check if tier matches expected options
                    tier_matches = tier in test_case["expected_tier_options"]
                    
                    # Verify tier matches score ranges from blueprint
                    score_tier_mapping = {
                        "Exceptional Value": (90, 100),
                        "Worth Buying": (75, 89),
                        "Acceptable but Overpriced": (60, 74),
                        "Poor Value": (40, 59),
                        "Marketing-Driven Product": (0, 39)
                    }
                    
                    if tier in score_tier_mapping:
                        min_score, max_score = score_tier_mapping[tier]
                        score_in_range = min_score <= score <= max_score
                    else:
                        score_in_range = False
                    
                    if tier_matches and score_in_range:
                        self.log_test(f"Tier Label: {test_case['name']}", True, f"Score: {score}, Tier: {tier}")
                    else:
                        self.log_test(f"Tier Label: {test_case['name']}", False, f"Score: {score}, Tier: {tier}, Expected: {test_case['expected_tier_options']}")
                else:
                    self.log_test(f"Tier Label: {test_case['name']}", False, f"API Error: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Tier Label: {test_case['name']}", False, f"Error: {str(e)}")

    def test_safety_penalties(self):
        """Test Component D Safety penalties for pregnancy avoid and high irritation"""
        # Test with ingredients that should trigger safety penalties
        test_cases = [
            {
                "name": "Pregnancy Avoid Penalty (-4 points)",
                "ingredients": "Aqua, Retinol, Glycerin",  # Retinol should be pregnancy avoid
                "expected_penalty": True
            },
            {
                "name": "High Irritation Penalty (-3 points)", 
                "ingredients": "Aqua, Glycolic Acid, Glycerin",  # Glycolic Acid high irritation
                "expected_penalty": True
            },
            {
                "name": "Safe Ingredients (No Penalty)",
                "ingredients": "Aqua, Glycerin, Panthenol, Sodium Hyaluronate",
                "expected_penalty": False
            }
        ]
        
        for test_case in test_cases:
            try:
                payload = {
                    "ingredients": test_case["ingredients"],
                    "price": 349,
                    "size_ml": 30,
                    "category": "Serum",
                    "skin_concerns": ["Hydration"],
                    "skin_type": "normal", 
                    "country": "India"
                }
                
                response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    safety_score = data['component_scores'].get('D', 10)
                    safety_details = data['component_details'].get('D', [])
                    
                    # Check if penalty was applied (score < 10)
                    penalty_applied = safety_score < 10
                    
                    # Look for safety-related details
                    safety_mentions = any('pregnancy' in str(detail).lower() or 'irritation' in str(detail).lower() 
                                        for detail in safety_details)
                    
                    if test_case["expected_penalty"]:
                        success = penalty_applied or safety_mentions
                        self.log_test(f"Safety Penalty: {test_case['name']}", success, 
                                    f"Safety Score: {safety_score}, Details: {safety_details[:2]}")
                    else:
                        success = safety_score >= 8  # Should be high for safe ingredients
                        self.log_test(f"Safety Penalty: {test_case['name']}", success,
                                    f"Safety Score: {safety_score}")
                else:
                    self.log_test(f"Safety Penalty: {test_case['name']}", False, f"API Error: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Safety Penalty: {test_case['name']}", False, f"Error: {str(e)}")

    def test_price_bands(self):
        """Test Component E Price Rationality bands"""
        # Test different price ratios according to blueprint
        test_cases = [
            {
                "name": "Low Price Ratio (<0.70) - Should get 10 points",
                "price": 100,  # Very low price
                "size_ml": 30,
                "expected_score_range": (9, 10)
            },
            {
                "name": "Medium Price Ratio (0.70-1.30) - Should get 8 points", 
                "price": 400,  # Average price
                "size_ml": 30,
                "expected_score_range": (7, 9)
            },
            {
                "name": "High Price Ratio (>2.00) - Should get 2 points",
                "price": 1500,  # Very high price
                "size_ml": 30,
                "expected_score_range": (2, 4)
            }
        ]
        
        for test_case in test_cases:
            try:
                payload = {
                    "ingredients": "Aqua, Niacinamide, Glycerin, Sodium Hyaluronate",
                    "price": test_case["price"],
                    "size_ml": test_case["size_ml"], 
                    "category": "Serum",
                    "skin_concerns": ["Hydration"],
                    "skin_type": "normal",
                    "country": "India"  # Use India for consistent pricing
                }
                
                response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    price_score = data['component_scores'].get('E', 0)
                    price_analysis = data.get('price_analysis', {})
                    
                    min_score, max_score = test_case["expected_score_range"]
                    score_in_range = min_score <= price_score <= max_score
                    
                    self.log_test(f"Price Band: {test_case['name']}", score_in_range,
                                f"Price Score: {price_score}, Ratio: {price_analysis.get('vs_average', 'N/A')}")
                else:
                    self.log_test(f"Price Band: {test_case['name']}", False, f"API Error: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Price Band: {test_case['name']}", False, f"Error: {str(e)}")

    def test_new_concerns(self):
        """Test that new concerns (Sun Protection, UV Damage, Tanning, Puffiness) work properly"""
        new_concerns = ['Sun Protection', 'UV Damage', 'Tanning', 'Puffiness']
        
        for concern in new_concerns:
            try:
                payload = {
                    "ingredients": "Aqua, Zinc Oxide, Titanium Dioxide, Caffeine, Alpha Arbutin, Kojic Acid, Ferulic Acid, Ascorbic Acid",
                    "price": 400,
                    "size_ml": 30,
                    "category": "Serum",
                    "skin_concerns": [concern],
                    "skin_type": "normal",
                    "country": "India"
                }
                
                response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    concern_fit = data.get('skin_concern_fit', {})
                    
                    # Check if the new concern appears in the response
                    if concern in concern_fit:
                        score = concern_fit[concern].get('score', 0)
                        self.log_test(f"New Concern: {concern}", True, f"Score: {score}%, Found in response")
                    else:
                        self.log_test(f"New Concern: {concern}", False, f"Concern not found in response: {list(concern_fit.keys())}")
                else:
                    self.log_test(f"New Concern: {concern}", False, f"API Error: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"New Concern: {concern}", False, f"Error: {str(e)}")

    def test_concern_names(self):
        """Test that concern names use full display names"""
        expected_concerns = [
            'Acne & Oily Skin', 'Aging & Fine Lines', 'Barrier Repair', 
            'Sensitive Skin', 'Large Pores', 'Uneven Texture'
        ]
        
        try:
            payload = {
                "ingredients": "Aqua, Niacinamide, Salicylic Acid, Retinol, Ceramide, Panthenol, Glycolic Acid",
                "price": 400,
                "size_ml": 30,
                "category": "Serum",
                "skin_concerns": expected_concerns,
                "skin_type": "combination",
                "country": "India"
            }
            
            response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                concern_fit = data.get('skin_concern_fit', {})
                
                # Check if all expected concerns are present in response
                found_concerns = list(concern_fit.keys())
                missing_concerns = [c for c in expected_concerns if c not in found_concerns]
                
                if len(missing_concerns) == 0:
                    self.log_test("Concern Names Format", True, f"All concerns found: {found_concerns}")
                else:
                    self.log_test("Concern Names Format", False, f"Missing concerns: {missing_concerns}")
            else:
                self.log_test("Concern Names Format", False, f"API Error: {response.status_code}")
                
        except Exception as e:
            self.log_test("Concern Names Format", False, f"Error: {str(e)}")

    def test_facial_oil_category(self):
        """Test that 'Facial Oil' category works instead of 'Oil'"""
        try:
            payload = {
                "ingredients": "Squalane, Jojoba Oil, Rosehip Oil, Vitamin E",
                "price": 500,
                "size_ml": 30,
                "category": "Facial Oil",  # New category name
                "skin_concerns": ["Hydration", "Barrier Repair"],
                "skin_type": "dry",
                "country": "India"
            }
            
            response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # Should get valid analysis without errors
                has_score = 'main_worth_score' in data
                has_tier = 'main_worth_tier' in data
                
                if has_score and has_tier:
                    self.log_test("Facial Oil Category", True, f"Score: {data['main_worth_score']}, Tier: {data['main_worth_tier']}")
                else:
                    self.log_test("Facial Oil Category", False, f"Missing score or tier in response")
            else:
                self.log_test("Facial Oil Category", False, f"API Error: {response.status_code}, {response.text}")
                
        except Exception as e:
            self.log_test("Facial Oil Category", False, f"Error: {str(e)}")

    def test_updated_tier_labels(self):
        """Test updated tier labels: 60-74 = 'Acceptable but Overpriced', 40-59 = 'Poor Value'"""
        # Test specific score ranges to verify tier labels
        test_cases = [
            {
                "name": "Score 60-74 Range Test",
                "ingredients": "Aqua, Glycerin, Parfum, Alcohol Denat",  # Basic ingredients with some penalties
                "price": 600,  # Moderate overpricing
                "expected_tier": "Acceptable but Overpriced"
            },
            {
                "name": "Score 40-59 Range Test", 
                "ingredients": "Aqua, Parfum, Alcohol Denat, Essential Oil, Limonene",  # Poor ingredients
                "price": 800,  # High overpricing
                "expected_tier": "Poor Value"
            }
        ]
        
        for test_case in test_cases:
            try:
                payload = {
                    "ingredients": test_case["ingredients"],
                    "price": test_case["price"],
                    "size_ml": 30,
                    "category": "Serum",
                    "skin_concerns": ["Hydration"],
                    "skin_type": "normal",
                    "country": "India"
                }
                
                response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    actual_tier = data.get('main_worth_tier', '')
                    actual_score = data.get('main_worth_score', 0)
                    
                    # Check if tier matches expected (allowing some flexibility in score boundaries)
                    tier_matches = actual_tier == test_case["expected_tier"]
                    
                    if tier_matches:
                        self.log_test(f"Updated Tier: {test_case['name']}", True, 
                                    f"Score: {actual_score}, Tier: {actual_tier}")
                    else:
                        self.log_test(f"Updated Tier: {test_case['name']}", False,
                                    f"Score: {actual_score}, Got: '{actual_tier}', Expected: '{test_case['expected_tier']}'")
                else:
                    self.log_test(f"Updated Tier: {test_case['name']}", False, f"API Error: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Updated Tier: {test_case['name']}", False, f"Error: {str(e)}")

    def test_fuzzy_matching(self):
        """Test fuzzy matching for ingredient names with typos"""
        test_cases = [
            {
                "name": "Niacinamid (missing 'e')",
                "ingredients": "Aqua, Niacinamid, Glycerin",
                "should_match": "Niacinamide"
            },
            {
                "name": "Glycerine (extra 'e')", 
                "ingredients": "Aqua, Glycerine, Panthenol",
                "should_match": "Glycerin"
            }
        ]
        
        for test_case in test_cases:
            try:
                payload = {
                    "ingredients": test_case["ingredients"],
                    "price": 349,
                    "size_ml": 30,
                    "category": "Serum", 
                    "skin_concerns": ["Hydration"],
                    "skin_type": "normal",
                    "country": "India"
                }
                
                response = requests.post(f"{API_BASE}/analyze", json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    identified_actives = data.get('identified_actives', [])
                    component_details = data.get('component_details', {})
                    
                    # Check if the ingredient was recognized (fuzzy matched)
                    # Look for mentions in actives or component details
                    fuzzy_matched = False
                    
                    # Check identified actives
                    for active in identified_actives:
                        if test_case["should_match"].lower() in active.get('name', '').lower():
                            fuzzy_matched = True
                            break
                    
                    # Check component details for mentions
                    if not fuzzy_matched:
                        for component_list in component_details.values():
                            for detail in component_list:
                                if test_case["should_match"].lower() in str(detail).lower():
                                    fuzzy_matched = True
                                    break
                    
                    self.log_test(f"Fuzzy Matching: {test_case['name']}", fuzzy_matched,
                                f"Expected match for '{test_case['should_match']}'")
                else:
                    self.log_test(f"Fuzzy Matching: {test_case['name']}", False, f"API Error: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Fuzzy Matching: {test_case['name']}", False, f"Error: {str(e)}")

    def test_fetch_barcode(self):
        """Test /api/fetch-product with barcode (Open Beauty Facts)"""
        try:
            # Test with a known barcode format
            payload = {"barcode": "8901030894260"}  # Example barcode
            
            response = requests.post(f"{API_BASE}/fetch-product", json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Fetch Product - Barcode", True, 
                            f"Source: {data.get('source', 'unknown')}, Has ingredients: {bool(data.get('ingredients'))}")
            elif response.status_code == 404:
                # Product not found is acceptable for Open Beauty Facts
                self.log_test("Fetch Product - Barcode", True, "Product not found (expected for some barcodes)")  
            else:
                self.log_test("Fetch Product - Barcode", False, f"Unexpected status: {response.status_code}")
                
        except Exception as e:
            self.log_test("Fetch Product - Barcode", False, f"Error: {str(e)}")

    def test_fetch_url_without_scraperapi(self):
        """Test /api/fetch-product with URL (should return error about missing ScraperAPI key)"""
        try:
            payload = {"url": "https://example.com/product"}
            
            response = requests.post(f"{API_BASE}/fetch-product", json=payload, timeout=15)
            data = response.json() if response.content else {}
            
            # Should return 500 with error about missing ScraperAPI key
            if response.status_code == 500 and 'ScraperAPI key not configured' in data.get('error', ''):
                self.log_test("Fetch Product - URL (No ScraperAPI)", True, "Correctly returns ScraperAPI key missing error")
            else:
                self.log_test("Fetch Product - URL (No ScraperAPI)", False, 
                            f"Status: {response.status_code}, Error: {data.get('error', 'No error message')}")
                
        except Exception as e:
            self.log_test("Fetch Product - URL (No ScraperAPI)", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all test suites"""
        print("🧪 Starting Skincare Worth Calculator API Tests")
        print("=" * 60)
        
        # Core functionality tests
        self.test_health_endpoint()
        self.test_analyze_basic()
        
        # New features tests (Second iteration)
        self.test_new_concerns()
        self.test_facial_oil_category() 
        self.test_updated_tier_labels()
        
        # Scoring logic tests 
        self.test_tier_labels()
        self.test_safety_penalties()
        self.test_price_bands()
        
        # Feature tests
        self.test_concern_names()
        self.test_fuzzy_matching() 
        
        # External API tests
        self.test_fetch_barcode()
        self.test_fetch_url_without_scraperapi()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return True
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} test(s) failed")
            return False

def main():
    tester = SkincareAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())